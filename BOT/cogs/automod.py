import json
import asyncio
import aiohttp
import datetime
import humanfriendly

from discord import (
    AutoModTrigger,
    AutoModRuleTriggerType,
    AutoModRuleAction,
    AutoModRuleEventType,
    TextChannel,
    Interaction,
    Embed,
    Message,
    utils,
    User,
    abc,
    Member,
    Object,
)

from discord.ext.commands import (
    Cog,
    hybrid_group,
    has_guild_permissions,
    bot_has_guild_permissions,
    TextChannelConverter,
)

from typing import Tuple, List
from collections import defaultdict

from tools.bot import Pretend
from tools.converters import NoStaff
from tools.validators import ValidTime
from tools.helpers import PretendContext
from tools.predicates import antispam_enabled


class Automod(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Automod commands"
        self.spam_cache = {}
        self.joins_cache = {}
        self.locks = defaultdict(asyncio.Lock)

    def antispam_threshold(self, message: Message):
        if not self.spam_cache.get(message.guild.id):
            self.spam_cache[message.guild.id]: dict = {}

        if not self.spam_cache[message.guild.id].get(message.author.id):
            self.spam_cache[message.guild.id][message.author.id]: List[
                Tuple[datetime.datetime, Message]
            ] = [(datetime.datetime.now(), message)]
        else:
            self.spam_cache[message.guild.id][message.author.id].append(
                (datetime.datetime.now(), message)
            )

        to_remove = [
            d
            for d in self.spam_cache[message.guild.id][message.author.id]
            if (datetime.datetime.now() - d[0]).total_seconds() > 10
        ]
        for d in to_remove:
            self.spam_cache[message.guild.id][message.author.id].remove(d)

        return list(
            map(lambda m: m[1], self.spam_cache[message.guild.id][message.author.id])
        )

    async def whitelisted_antispam(self, message: Message):
        res = await self.bot.db.fetchrow(
            "SELECT users, channels FROM antispam WHERE guild_id = $1", message.guild.id
        )
        if res["users"]:
            users = json.loads(res["users"])
            if message.author.id in users:
                return True

        if res["channels"]:
            channels = json.loads(res["channels"])
            if message.channel.id in channels:
                return True

        return False

    def get_joins(self, member: Member) -> int:
        if self.joins_cache.get(member.guild.id):
            self.joins_cache[member.guild.id].append(
                (datetime.datetime.now(), member.id)
            )
            to_remove = [
                m
                for m in self.joins_cache[member.guild.id]
                if (datetime.datetime.now() - m[0]).total_seconds() > 5
            ]

            for r in to_remove:
                self.joins_cache[member.guild.id].remove(r)

        else:
            self.joins_cache[member.guild.id] = [(datetime.datetime.now(), member.id)]

        return len(self.joins_cache[member.guild.id])

    @Cog.listener("on_guild_channel_delete")
    async def whitelisted_channel_delete(self, channel: abc.GuildChannel):
        if str(channel.type) == "text":
            check = await self.bot.db.fetchval(
                "SELECT channels FROM antispam WHERE guild_id = $1", channel.guild.id
            )
            if check:
                channels = json.loads(check["channels"])
                if channel.id in channels:
                    channels.remove(channel.id)
                    await self.bot.db.execute(
                        "UPDATE antispam SET channels = $1 WHERE guild_id = $2",
                        json.dumps(channels),
                        channel.guild.id,
                    )

    @Cog.listener("on_member_join")
    async def mass_join_event(self, member: Member):
        if member.guild.me.guild_permissions.administrator:
            if rate := await self.bot.db.fetchval(
                "SELECT rate FROM anti_join WHERE guild_id = $1", member.guild.id
            ):
                joins = self.get_joins(member)
                if joins > rate:
                    async with self.locks[member.guild.id]:
                        tasks = [
                            member.guild.ban(
                                user=Object(m[1]),
                                reason="Flagged by mass join protection",
                            )
                            for m in self.joins_cache[member.guild.id]
                        ]
                        await asyncio.gather(*tasks)
                        self.joins_cache = []

                        url = f"https://discord.com/api/v9/guilds/{member.guild.id}/incident-actions"
                        until = (
                            utils.utcnow() + datetime.timedelta(minutes=30)
                        ).isoformat()

                        headers = {
                            "Authorization": f"Bot {self.bot.http.token}",
                            "Content-Type": "application/json",
                        }

                        data = {
                            "dms_disabled_until": until,
                            "invites_disabled_until": until,
                        }

                        async with aiohttp.ClientSession(headers=headers) as cs:
                            async with cs.put(url, json=data) as r:
                                print(r.status)

    @Cog.listener("on_message")
    async def antispam_event(self, message: Message):
        if message.guild:
            if not message.guild.chunked:
                await message.guild.chunk(cache=True)
            if isinstance(message.author, User):
                return
            if not message.author.guild_permissions.manage_guild:
                if message.guild.me.guild_permissions.moderate_members:
                    if message.guild.me.top_role:
                        if message.author.top_role:
                            if message.author.top_role >= message.guild.me.top_role:
                                return
                    else:
                        return

                    if check := await self.bot.db.fetchrow(
                        "SELECT * FROM antispam WHERE guild_id = $1", message.guild.id
                    ):
                        if not await self.whitelisted_antispam(message):
                            messages = self.antispam_threshold(message)
                            if len(messages) > check["rate"]:
                                res = self.bot.cache.get(
                                    f"antispam-{message.author.id}"
                                )
                                if not res:
                                    del self.spam_cache[message.guild.id][
                                        message.author.id
                                    ]
                                    timeout = utils.utcnow() + datetime.timedelta(
                                        seconds=check["timeout"]
                                    )
                                    await message.channel.delete_messages(messages)
                                    await message.author.timeout(
                                        timeout, reason="Flagged by the antispam"
                                    )
                                    await message.channel.send(
                                        embed=Embed(
                                            color=self.bot.warning_color,
                                            description=f"> {self.bot.warning} {message.author.mention} has been muted for **{humanfriendly.format_timespan(check['timeout'])}** - ***spamming messages***",
                                        ),
                                        delete_after=5,
                                    )
                                    await self.bot.cache.set(
                                        f"antispam-{message.author.id}",
                                        True,
                                        expiration=10,
                                    )

    @hybrid_group(name="filter", invoke_without_command=True)
    async def chat_filter(self, ctx):
        await ctx.create_pages()

    @chat_filter.group(name="joins", invoke_without_command=True)
    async def filter_joins(self, ctx):
        """prevent join raids on your server"""
        return await ctx.create_pages()

    @filter_joins.command(name="enable", brief="administrator", aliases=["e"])
    @has_guild_permissions(administrator=True)
    async def filter_joins_enable(self, ctx: PretendContext):
        """enable mass join protection"""
        if await self.bot.db.fetchrow(
            "SELECT * FROM anti_join WHERE guild_id = $1", ctx.guild.id
        ):
            return await ctx.send_error("Mass join protection is **already** enabled")

        await self.bot.db.execute(
            "INSERT INTO anti_join VALUES ($1,$2)", ctx.guild.id, 7
        )
        return await ctx.send_success(
            "Enabled **mass join** protection\nRate: **7** joins per **5** seconds allowed"
        )

    @filter_joins.command(name="disable", brief="administrator", aliases=["dis"])
    @has_guild_permissions(administrator=True)
    async def filter_joins_disable(self, ctx: PretendContext):
        """disable mass join protection"""
        if not await self.bot.db.fetchrow(
            "SELECT * FROM anti_join WHERE guild_id = $1", ctx.guild.id
        ):
            return await ctx.send_error("Mass join protection is **not** enabled")

        await self.bot.db.execute(
            "DELETE FROM anti_join WHERE guild_id = $1", ctx.guild.id
        )
        return await ctx.send_success("Disabled mass join protection")

    @filter_joins.command(name="rate", brief="administrator")
    @has_guild_permissions(administrator=True)
    async def filter_joins_rate(self, ctx: PretendContext, rate: int):
        """change the number of allowed members to join per 5 seconds before triggering anti mass join"""
        if await self.bot.db.fetchrow(
            "SELECT * FROM anti_join WHERE guild_id = $1", ctx.guild.id
        ):
            await self.bot.db.execute(
                "UPDATE anti_join SET rate = $1 WHERE guild_id = $2", rate, ctx.guild.id
            )
        else:
            return await ctx.send_warning("Mass join protection is **not** enabled")

        await ctx.send_success(
            f"Changed mass join rate to **{rate}** joins per **5** seconds"
        )

    @chat_filter.group(name="spam", invoke_without_command=True)
    async def chat_filter_spam(self, ctx):
        """prevent people from spamming messages"""
        return await ctx.create_pages()

    @chat_filter_spam.command(name="enable", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def chat_filter_spam_enable(self, ctx: PretendContext):
        """enable the protection against message spamming"""
        if not await self.bot.db.fetchrow(
            "SELECT * FROM antispam WHERE guild_id = $1", ctx.guild.id
        ):
            await self.bot.db.execute(
                "INSERT INTO antispam (guild_id, rate, timeout) VALUES ($1,$2,$3)",
                ctx.guild.id,
                8,
                120,
            )
            return await ctx.send_success(
                "Anti spam is **now** enabled\nRate: **8** messages in **10 seconds**\nTimeout punishment: **2 minutes**"
            )

    @chat_filter_spam.command(name="disable", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @antispam_enabled()
    async def chat_filter_spam_disable(self, ctx: PretendContext):
        """disable the protection against message spamming"""

        async def yes_func(interaction: Interaction):
            await interaction.client.db.execute(
                "DELETE FROM antispam WHERE guild_id = $1", ctx.guild.id
            )
            return await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.yes_color,
                    description=f"{interaction.client.yes} {interaction.user.mention}: Disabled the anti spam",
                ),
                view=None,
            )

        async def no_func(interaction: Interaction):
            return await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.color,
                    description=f"{interaction.user.mention} changed their mind",
                ),
                view=None,
            )

        return await ctx.confirmation_send(
            "Are you sure you want to **disable** the anti spam", yes_func, no_func
        )

    @chat_filter_spam.command(name="rate", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @antispam_enabled()
    async def chat_filter_spam_rate(self, ctx: PretendContext, rate: int):
        """change the limit of sending messages per 10 seconds"""
        if rate < 2:
            return await ctx.send_warning("The rate cannot be lower than **2**")

        await self.bot.db.execute(
            "UPDATE antispam SET rate = $1 WHERE guild_id = $2", rate, ctx.guild.id
        )
        return await ctx.send_success(
            f"Modified rate\nNew rate: **{rate}** messages per **10 seconds**"
        )

    @chat_filter_spam.command(name="timeout", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @antispam_enabled()
    async def chat_filter_spam_timeout(self, ctx: PretendContext, time: ValidTime):
        """modify the amount of time the users will be timed out for spamming"""
        await self.bot.db.execute(
            "UPDATE antispam SET timeout = $1 WHERE guild_id = $2", time, ctx.guild.id
        )
        return await ctx.send_success(
            f"Modified time out punishment\nTimeout punishment: **{humanfriendly.format_timespan(time)}**"
        )

    @chat_filter_spam.command(name="settings", aliases=["stats", "statistics"])
    @antispam_enabled()
    async def chat_filter_spam_settings(self, ctx: PretendContext):
        """check the settings for antispam"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antispam WHERE guild_id = $1", ctx.guild.id
        )
        if not check["users"]:
            whitelisted_users = "none"
        else:
            whitelisted_users = (
                ", ".join(list(map(lambda m: f"<@{m}>", json.loads(check["users"]))))
                if len(json.loads(check["users"])) < 5
                else ", ".join(
                    list(map(lambda m: f"<@{m}>", json.loads(check["users"])[:5]))
                )
                + f" and {len(check['users'])-5} more..."
            )

        if not check["channels"]:
            whitelisted_channels = "none"
        else:
            whitelisted_channels = (
                ", ".join(list(map(lambda m: f"<@{m}>", json.loads(check["channels"]))))
                if len(json.loads(check["channels"])) < 5
                else ", ".join(
                    list(map(lambda m: f"<@{m}>", json.loads(check["channels"])[:5]))
                )
                + f" and {len(check['channels'])-5} more..."
            )

        embed = Embed(color=self.bot.color)
        embed.set_author(
            name=f"{ctx.guild.name}'s antispam stats", icon_url=ctx.guild.icon
        )

        embed.add_field(
            name="rate",
            value=f"**{check['rate']}** msgs per **10 seconds**",
            inline=False,
        )

        embed.add_field(
            name="punishment",
            value=f"timeout for **{humanfriendly.format_timespan(check['timeout'])}**",
            inline=False,
        )

        embed.add_field(name="Whitelisted users", value=whitelisted_users, inline=False)

        embed.add_field(
            name="Whitelisted channels", value=whitelisted_channels, inline=False
        )

        await ctx.send(embed=embed)

    @chat_filter_spam.command(
        name="unwhitelist",
        aliases=["uwl"],
        brief="manage server",
        usage="example: ;filter spam unwhitelist user @qrscan (types can be user or channel)",
    )
    @has_guild_permissions(manage_guild=True)
    @antispam_enabled()
    async def chat_filter_spam_unwhitelist(
        self, ctx: PretendContext, type: str, *, target: str
    ):
        """unwhitelist the whitelisted channels and users from antispam"""
        if type == "user":
            user = await NoStaff().convert(ctx, target)
            return await self.chat_filter_spam_uwl_user(ctx, user)
        elif type == "channel":
            channel = await TextChannelConverter().convert(ctx, target)
            return await self.chat_filter_spam_uwl_channel(ctx, channel)
        else:
            return await ctx.send_warning("Available types: user, channel")

    async def chat_filter_spam_uwl_user(self, ctx: PretendContext, member: NoStaff):
        """unwhitelist an user from antispam"""
        check = await self.bot.db.fetchval(
            "SELECT users FROM antispam WHERE guild_id = $1", ctx.guild.id
        )
        if check:
            check = json.loads(check)

            if not member.id in check:
                return await ctx.send_warning(
                    "This user is **not** anti spam whitelisted"
                )

            check.remove(member.id)
        else:
            return await ctx.send_warning("This user is **not** anti spam whitelisted")

        await self.bot.db.execute(
            "UPDATE antispam SET users = $1 WHERE guild_id = $2",
            json.dumps(check),
            ctx.guild.id,
        )
        return await ctx.send_success(f"Unwhitelisted {member.mention} from anti spam")

    async def chat_filter_spam_uwl_channel(
        self, ctx: PretendContext, channel: TextChannel
    ):
        """unwhitelist an user from antispam"""
        check = await self.bot.db.fetchval(
            "SELECT channels FROM antispam WHERE guild_id = $1", ctx.guild.id
        )
        if check:
            check = json.loads(check)

            if not channel.id in check:
                return await ctx.send_warning(
                    "This channel is **not** anti spam whitelisted"
                )

            check.remove(channel.id)
        else:
            return await ctx.send_warning(
                "This channel is **not** anti spam whitelisted"
            )

        await self.bot.db.execute(
            "UPDATE antispam SET channels = $1 WHERE guild_id = $2",
            json.dumps(check),
            ctx.guild.id,
        )
        return await ctx.send_success(f"Unwhitelisted {channel.mention} from anti spam")

    @chat_filter_spam.command(
        name="whitelist",
        aliases=["wl"],
        brief="manage server",
        usage="example: ;filter spam whitelist user @qrscan (types can be user or channel)",
    )
    @has_guild_permissions(manage_guild=True)
    @antispam_enabled()
    async def chat_filter_spam_whitelist(
        self, ctx: PretendContext, type: str, *, target: str
    ):
        """manage the users and channels where spamming is allowed"""
        if type == "user":
            user = await NoStaff().convert(ctx, target)
            return await self.chat_filter_spam_wl_user(ctx, user)
        elif type == "channel":
            channel = await TextChannelConverter().convert(ctx, target)
            return await self.chat_filter_spam_wl_channel(ctx, channel)
        else:
            return await ctx.send_warning("Available types: user, channel")

    async def chat_filter_spam_wl_channel(
        self, ctx: PretendContext, channel: TextChannel
    ):
        """whitelist a channel from antispam"""
        check = await self.bot.db.fetchval(
            "SELECT channels FROM antispam WHERE guild_id = $1", ctx.guild.id
        )
        if check:
            check = json.loads(check)

            if channel.id in check:
                return await ctx.send_warning(
                    "This channel is **already** anti spam whitelisted"
                )

            check.append(channel.id)
        else:
            check = [channel.id]

        await self.bot.db.execute(
            "UPDATE antispam SET channels = $1 WHERE guild_id = $2",
            json.dumps(check),
            ctx.guild.id,
        )
        return await ctx.send_success(f"Whitelisted {channel.mention} from anti spam")

    async def chat_filter_spam_wl_user(self, ctx: PretendContext, member: NoStaff):
        """whitelist an user for antispam"""
        check = await self.bot.db.fetchval(
            "SELECT users FROM antispam WHERE guild_id = $1", ctx.guild.id
        )
        if check:
            check = json.loads(check)

            if member.id in check:
                return await ctx.send_warning(
                    "This user is **already** anti spam whitelisted"
                )

            check.append(member.id)
        else:
            check = [member.id]

        await self.bot.db.execute(
            "UPDATE antispam SET users = $1 WHERE guild_id = $2",
            json.dumps(check),
            ctx.guild.id,
        )
        return await ctx.send_success(f"Whitelisted {member.mention} from anti spam")

    @chat_filter.group(name="invites", invoke_without_command=True)
    async def chat_filter_invites(self, ctx):
        """prevent people from sending discord invite links"""
        await ctx.create_pages()

    @chat_filter_invites.command(name="enable", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_guild=True)
    async def chat_filter_invites_enable(self, ctx: PretendContext):
        """
        Enable the invite filter
        """

        check = await self.bot.db.fetchrow(
            "SELECT rule_id FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "invites",
        )
        if not check:
            trigger = AutoModTrigger(
                type=AutoModRuleTriggerType.keyword,
                regex_patterns=[
                    r"(https?://)?(www.)?(discord.(gg|io|me|li)|discordapp.com/invite|discord.com/invite)/.+[a-z]"
                ],
            )
            mod = await ctx.guild.create_automod_rule(
                name=f"{self.bot.user.name}-antilink",
                event_type=AutoModRuleEventType.message_send,
                trigger=trigger,
                enabled=True,
                actions=[
                    AutoModRuleAction(
                        custom_message=f"Message blocked by {self.bot.user.name} for containing an invite link"
                    )
                ],
                reason="Filter invites rule created",
            )
            await self.bot.db.execute(
                "INSERT INTO filter VALUES ($1,$2,$3)", ctx.guild.id, "invites", mod.id
            )
            return await ctx.send_success(f"Enabled the filter for discord invites")
        else:
            mod = await ctx.guild.fetch_automod_rule(check[0])
            if mod:
                if not mod.enabled:
                    await mod.edit(
                        enabled=True, reason=f"invites filter enabled by {ctx.author}"
                    )
                    return await ctx.send_success(
                        f"Enabled the filter for discord invites"
                    )
                return await ctx.send_warning(
                    "The filter for discord invites is **already** enabled"
                )
            return await ctx.send_error("The automod rule was not found")

    @chat_filter_invites.command(name="disable", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_guild=True)
    async def chat_filter_invites_disable(self, ctx: PretendContext):
        """disable the filter for discord invites"""
        check = await self.bot.db.fetchrow(
            "SELECT rule_id FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "invites",
        )

        if not check:
            return await ctx.send_warning("Invites filter is **not** enabled")

        mod = await ctx.guild.fetch_automod_rule(check[0])

        if mod:
            await mod.delete(reason=f"invites filter disabled by {ctx.author}")
            await ctx.send_success("Disabled the filter for discord invites")

        else:
            await ctx.send_error("The automod rule was not found")

        await self.bot.db.execute(
            "DELETE FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "invites",
        )

    @chat_filter_invites.command(
        name="whitelist", brief="manage server", aliases=["wl", "exempt"]
    )
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_guild=True)
    async def chat_filter_invites_whitelist(
        self, ctx: PretendContext, *, channel: TextChannel
    ):
        """make channels imune from the invites filter"""
        check = await self.bot.db.fetchrow(
            "SELECT rule_id FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "invites",
        )

        if not check:
            return await ctx.send_warning("Invites filter is **not** configured")

        mod = await ctx.guild.fetch_automod_rule(check[0])

        if not mod:
            return await ctx.send_error(
                "Unable to find the **invites filter** automod rule. Please clear it and create a new one"
            )

        if channel.id in mod.exempt_channel_ids:
            return await ctx.send_error("This channel is **already** exempted")

        channels = mod.exempt_channels
        channels.append(channel)
        await mod.edit(
            exempt_channels=channels,
            reason=f"Invites filter rule edited by {ctx.author}",
        )

        await ctx.send_success(
            f"{channel.mention} is now **exempted** from the invites filter"
        )

    @chat_filter_invites.command(
        name="unwhitelist", brief="manage server", aliases=["uwl"]
    )
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_guild=True)
    async def chat_filter_invites_unwhitelist(
        self, ctx: PretendContext, *, channel: TextChannel
    ):
        """remove the channel's immunity from the invites filter"""
        check = await self.bot.db.fetchrow(
            "SELECT rule_id FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "invites",
        )

        if not check:
            return await ctx.send_warning("Invites filter is **not** configured")

        mod = await ctx.guild.fetch_automod_rule(check[0])

        if not mod:
            return await ctx.send_error(
                "Unable to find the **invites filter** automod rule. Please clear it and create a new one"
            )

        if not channel.id in mod.exempt_channel_ids:
            return await ctx.send_error("This channel is **not** exempted")

        channels = mod.exempt_channels
        channels.remove(channel)
        await mod.edit(
            exempt_channels=channels,
            reason=f"Invites filter rule edited by {ctx.author}",
        )

        await ctx.send_success(
            f"{channel.mention} removed from the invites filter exempted channels"
        )

    @chat_filter_invites.command(name="whitelisted", aliases=["exempted"])
    async def chat_filter_invites_whitelisted(self, ctx: PretendContext):
        """returns the imune channels from the invites filter"""
        check = await self.bot.db.fetchrow(
            "SELECT rule_id FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "invites",
        )

        if not check:
            return await ctx.send_warning("Invites filter is **not** configured")

        mod = await ctx.guild.fetch_automod_rule(check[0])

        if not mod:
            return await ctx.send_error(
                "Unable to find the **invites filter** automod rule. Please clear it and create a new one"
            )

        if len(mod.exempt_channel_ids) == 0:
            return await ctx.send_error("No exempted channels for invites filter")

        await ctx.paginate(
            [f"<#{c}>" for c in mod.exempt_channel_ids],
            "Invites filter whitelisted",
            author={
                "name": self.bot.user.name,
                "icon_url": self.bot.user.display_avatar.url,
            },
        )

    @chat_filter.group(name="words", invoke_without_command=True)
    async def chat_filter_words(self, ctx):
        """keep the bad words away"""
        await ctx.create_pages()

    @chat_filter_words.command(name="add", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_guild=True)
    async def chat_filter_words_add(self, ctx: PretendContext, *, word: str):
        """add a word to the filter"""
        check = await self.bot.db.fetchrow(
            "SELECT rule_id FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "words",
        )
        if not check:
            trigger = AutoModTrigger(
                type=AutoModRuleTriggerType.keyword, keyword_filter=["*" + word + "*"]
            )

            mod = await ctx.guild.create_automod_rule(
                name=f"{self.bot.user.name}-chatfilter",
                event_type=AutoModRuleEventType.message_send,
                trigger=trigger,
                enabled=True,
                actions=[
                    AutoModRuleAction(
                        custom_message=f"Message blocked by {self.bot.user.name} for containing a word that cannot be used"
                    )
                ],
                reason="Filter words rule created",
            )

            await self.bot.db.execute(
                "INSERT INTO filter VALUES ($1,$2,$3)", ctx.guild.id, "words", mod.id
            )
            return await ctx.send_success(
                f"Created **word filter** with the word **{word}**"
            )
        else:
            mod = await ctx.guild.fetch_automod_rule(check[0])
            if not mod:
                return await ctx.send_error(
                    "Unable to find the **words filter** automod rule. Please clear it and create a new one"
                )
            filters = mod.trigger.keyword_filter
            filters.append("*" + word + "*")
            await mod.edit(
                trigger=AutoModTrigger(
                    type=AutoModRuleTriggerType.keyword, keyword_filter=filters
                ),
                reason=f"Words filter rule edited by {ctx.author}",
            )
            return await ctx.send_success(f"Added **{word}** to the words filter")

    @chat_filter_words.command(name="remove", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_guild=True)
    async def chat_filter_words_remove(self, ctx: PretendContext, *, word: str):
        """remove a word from the filter"""
        check = await self.bot.db.fetchrow(
            "SELECT rule_id FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "words",
        )

        if not check:
            return await ctx.send_warning("Word filter is **not** configured")

        mod = await ctx.guild.fetch_automod_rule(check[0])

        if not mod:
            return await ctx.send_error(
                "Unable to find the **words filter** automod rule. Please clear it and create a new one"
            )

        filters = mod.trigger.keyword_filter

        if not "*" + word + "*" in filters:
            return await ctx.send_warning(
                f"The word **{word}** is not in the word filter list"
            )

        filters.remove("*" + word + "*")
        await mod.edit(
            trigger=AutoModTrigger(
                type=AutoModRuleTriggerType.keyword, keyword_filter=filters
            ),
            reason=f"Words filter rule edited by {ctx.author}",
        )
        return await ctx.send_success(f"Removed **{word}** from the words filter")

    @chat_filter_words.command(name="clear", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_guild=True)
    async def chat_filter_words_clear(self, ctx: PretendContext):
        """delete the entire word rule"""
        check = await self.bot.db.fetchrow(
            "SELECT rule_id FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "words",
        )

        if not check:
            return await ctx.send_warning("Word filter is **not** configured")

        mod = await ctx.guild.fetch_automod_rule(check[0])

        if mod:
            await mod.delete(reason=f"Word filter cleared by {ctx.author}")

        await self.bot.db.execute(
            "DELETE FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "words",
        )
        return await ctx.send_success("Word filter has been clear")

    @chat_filter_words.command(name="list")
    async def chat_filter_words_list(self, ctx: PretendContext):
        """check a list of words that are not allowed in this server"""
        results = await self.bot.db.fetchrow(
            "SELECT rule_id FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "words",
        )

        if not results:
            return await ctx.send_warning("Word filter is **not** configured")

        mod = await ctx.guild.fetch_automod_rule(results[0])

        if not mod:
            return await ctx.send_error(
                "Unable to find the **words filter** automod rule. Please clear it and create a new one"
            )

        filters = [w[1:][:-1] for w in mod.trigger.keyword_filter]
        await ctx.paginate(
            filters,
            title=f"Filtered words ({len(filters)})",
            author={
                "name": self.bot.user.name,
                "icon_url": self.bot.user.display_avatar.url,
            },
        )

    @chat_filter_words.command(
        name="whitelist", brief="manage server", aliases=["wl", "exempt"]
    )
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_guild=True)
    async def chat_filter_words_whitelist(
        self, ctx: PretendContext, *, channel: TextChannel
    ):
        """make channels imune from the word filter"""
        check = await self.bot.db.fetchrow(
            "SELECT rule_id FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "words",
        )

        if not check:
            return await ctx.send_warning("Word filter is **not** configured")

        mod = await ctx.guild.fetch_automod_rule(check[0])

        if not mod:
            return await ctx.send_error(
                "Unable to find the **words filter** automod rule. Please clear it and create a new one"
            )

        if channel.id in mod.exempt_channel_ids:
            return await ctx.send_error("This channel is **already** exempted")

        channels = mod.exempt_channels
        channels.append(channel)
        await mod.edit(
            exempt_channels=channels, reason=f"Word filter rule edited by {ctx.author}"
        )
        await ctx.send_success(
            f"{channel.mention} is now **exempted** from the word filter"
        )

    @chat_filter_words.command(
        name="unwhitelist", brief="manage server", aliases=["uwl"]
    )
    @has_guild_permissions(manage_guild=True)
    @bot_has_guild_permissions(manage_guild=True)
    async def chat_filter_words_unwhitelist(
        self, ctx: PretendContext, *, channel: TextChannel
    ):
        """remove the channel's immunity from the words filter"""
        check = await self.bot.db.fetchrow(
            "SELECT rule_id FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "words",
        )

        if not check:
            return await ctx.send_warning("Word filter is **not** configured")

        mod = await ctx.guild.fetch_automod_rule(check[0])

        if not mod:
            return await ctx.send_error(
                "Unable to find the **words filter** automod rule. Please clear it and create a new one"
            )

        if not channel.id in mod.exempt_channel_ids:
            return await ctx.send_error("This channel is **not** exempted")

        channels = mod.exempt_channels
        channels.remove(channel)
        await mod.edit(
            exempt_channels=channels, reason=f"Word filter rule edited by {ctx.author}"
        )

        await ctx.send_success(
            f"{channel.mention} removed from the word filter exempted channels"
        )

    @chat_filter_words.command(name="whitelisted", aliases=["exempted"])
    async def chat_filter_words_whitelisted(self, ctx: PretendContext):
        """returns the imune channels from the words filter"""
        check = await self.bot.db.fetchrow(
            "SELECT rule_id FROM filter WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "words",
        )

        if not check:
            return await ctx.send_warning("Word filter is **not** configured")

        mod = await ctx.guild.fetch_automod_rule(check[0])

        if not mod:
            return await ctx.send_error(
                "Unable to find the **words filter** automod rule. Please clear it and create a new one"
            )

        if len(mod.exempt_channel_ids) == 0:
            return await ctx.send_error("No exempted channels for words filter")

        await ctx.paginate(
            [f"<#{c}>" for c in mod.exempt_channel_ids],
            "Words filter whitelisted",
            author={
                "name": self.bot.user.name,
                "icon_url": self.bot.user.display_avatar.url,
            },
        )


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Automod(bot))
