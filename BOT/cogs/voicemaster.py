import asyncio

from collections import defaultdict

from tools.bot import Pretend
from tools.helpers import PretendContext
from tools.handlers.embedbuilder import EmbedBuilder
from tools.persistent.vm import VoiceMasterView, ButtonScript
from tools.predicates import is_vm, check_vc_owner, rename_cooldown

from discord import (
    Member,
    VoiceState,
    VoiceChannel,
    Embed,
    PermissionOverwrite,
    CategoryChannel,
)
from discord.ext.commands import (
    Cog,
    hybrid_group,
    has_guild_permissions,
    command,
    bot_has_guild_permissions,
)


class Voicemaster(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "VoiceMaster commands"
        self.locks = defaultdict(asyncio.Lock)
        self.values = [
            ("<:lock:1188943564051325028>", "`lock` the voice channel"),
            ("<:unlock:1188945889423785984>", "`unlock` the voice channel"),
            ("<:ghost:1188943552995131452>", "`hide` the voice channel"),
            ("<:unghost:1188943588986462209>", "`reveal` the voice channel"),
            ("<:rename:1188943581843574915>", "`rename` the voice channel"),
            ("<:minus:1188945883472076870>", "`decrease` the member limit"),
            ("<:plus:1188945888433930350>", "`increase` the member limit"),
            ("<:info:1188946782277877760>", "`info` about the voice channel"),
            ("<:kick:1188943566123319429>", "`kick` someone from the voice channel"),
            ("<:claim:1188943555092287549>", "`claim` the voice channel"),
        ]

    async def get_channel_categories(
        self, channel: VoiceChannel, member: Member
    ) -> bool:
        """
        Check if there are maximum channels created in the voicemaster category
        """

        if len(channel.category.channels) == 50:
            await member.move_to(channel=None)

        return len(channel.category.channels) == 50

    async def get_channel_overwrites(
        self, channel: VoiceChannel, member: Member
    ) -> bool:
        """
        Check if the channel is locked by command. kicking admins that are not permitted
        """

        if not member.bot:
            if che := await self.bot.db.fetchrow(
                "SELECT * FROM vcs WHERE voice = $1", channel.id
            ):
                if che["user_id"] != member.id:
                    if (
                        channel.overwrites_for(channel.guild.default_role).connect
                        == False
                    ):
                        if (
                            channel.overwrites_for(member).connect == False
                            or channel.overwrites_for(member).connect is None
                        ):
                            if member.id != member.guild.owner_id:
                                try:
                                    return await member.move_to(
                                        channel=None,
                                        reason="not allowed to join this voice channel",
                                    )
                                except:
                                    pass

    async def create_temporary_channel(
        self, member: Member, category: CategoryChannel
    ) -> None:
        """
        Create a custom voice master voice channel
        """

        channel = await member.guild.create_voice_channel(
            name=f"{member.name}'s lounge",
            category=category,
            reason="creating temporary voice channel",
            overwrites=category.overwrites,
        )

        await member.move_to(channel=channel)
        await self.bot.db.execute(
            "INSERT INTO vcs VALUES ($1,$2)", member.id, channel.id
        )
        channel = await channel.guild.fetch_channel(channel.id)
        await asyncio.sleep(0.9)
        if channel is not None and len(channel.members) == 0:
            try:
                await channel.delete(reason="No one inside the temporary voice channel")
            except:
                pass
            await self.bot.db.execute("DELETE FROM vcs WHERE voice = $1", channel.id)
        return None

    async def delete_temporary_channel(self, channel: VoiceChannel) -> None:
        """
        Delete a custom voice master channel
        """

        if await self.bot.db.fetchrow("SELECT * FROM vcs WHERE voice = $1", channel.id):
            if len(channel.members) == 0:
                await self.bot.db.execute(
                    "DELETE FROM vcs WHERE voice = $1", channel.id
                )
                if channel:
                    self.bot.cache.delete(f"vc-bucket-{channel.id}")
                    await channel.delete(reason="no one in the temporary voice channel")

        return None

    @Cog.listener()
    async def on_voice_state_update(
        self, member: Member, before: VoiceState, after: VoiceState
    ):
        if (
            member.guild.me.guild_permissions.administrator
            and before.channel != after.channel
        ):
            if check := await self.bot.db.fetchrow(
                "SELECT * FROM voicemaster WHERE guild_id = $1", member.guild.id
            ):
                jtc = int(check["channel_id"])

                if not before.channel and after.channel:
                    if after.channel.id == jtc:

                        if await self.get_channel_categories(after.channel, member):
                            return

                        return await self.create_temporary_channel(
                            member, after.channel.category
                        )
                    else:
                        return await self.get_channel_overwrites(after.channel, member)

                elif before.channel and after.channel:
                    if before.channel.id == jtc:
                        return

                    if before.channel.category == after.channel.category:
                        if after.channel.id == jtc:
                            if await self.bot.db.fetchrow(
                                "SELECT * FROM vcs WHERE voice = $1", before.channel.id
                            ):
                                if len(before.channel.members) == 0:
                                    return await member.move_to(channel=before.channel)

                            if await self.get_channel_categories(after.channel, member):
                                return

                            return await self.create_temporary_channel(
                                member, after.channel.category
                            )
                        elif before.channel.id != after.channel.id:
                            await self.get_channel_overwrites(after.channel, member)
                            await self.delete_temporary_channel(before.channel)
                    else:
                        if after.channel.id == jtc:
                            if (
                                await self.get_channel_categories(after.channel, member)
                                is True
                            ):
                                return

                            return await self.create_temporary_channel(
                                member, after.channel.category
                            )
                        else:
                            await self.get_channel_overwrites(after.channel, member)
                            await self.delete_temporary_channel(before.channel)

                elif before.channel and not after.channel:
                    if before.channel.id == jtc:
                        return

                    await self.delete_temporary_channel(before.channel)

    @hybrid_group(invoke_without_command=True, aliases=["vm"])
    async def voicemaster(self, ctx: PretendContext):
        """
        Create custom voice channels
        """

        await ctx.create_pages()

    @voicemaster.command(name="setup", brief="administrator")
    @has_guild_permissions(administrator=True)
    @bot_has_guild_permissions(manage_channels=True)
    @is_vm()
    async def vm_setup(self, ctx: PretendContext):
        """
        Configure the voicemaster module
        """

        async with self.locks[ctx.guild.id]:
            mes = await ctx.send(
                embed=Embed(
                    color=self.bot.color,
                    description=f"{ctx.author.mention}: Creating the VoiceMaster interface",
                )
            )
            await self.bot.db.execute(
                "DELETE FROM vm_buttons WHERE guild_id = $1", ctx.guild.id
            )
            category = await ctx.guild.create_category(
                name="voicemaster", reason="voicemaster category created"
            )
            voice = await ctx.guild.create_voice_channel(
                name="join to create",
                category=category,
                reason="voicemaster channel created",
            )
            text = await ctx.guild.create_text_channel(
                name="interface",
                category=category,
                reason="voicemaster interface created",
                overwrites={
                    ctx.guild.default_role: PermissionOverwrite(send_messages=False)
                },
            )
            embed = Embed(
                color=self.bot.color,
                title="VoiceMaster Interface",
                description=f"Control the voice channels created from {voice.mention}",
            )
            embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon)
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            embed.set_footer(text="pretend")
            embed.add_field(
                name="usage", value="\n".join(f"{x[0]} - {x[1]}" for x in self.values)
            )
            view = VoiceMasterView(self.bot)
            await view.add_default_buttons(ctx.guild)
            await text.send(embed=embed, view=view)
            await self.bot.db.execute(
                """
          INSERT INTO voicemaster 
          VALUES ($1,$2,$3)
          """,
                ctx.guild.id,
                voice.id,
                text.id,
            )
            return await mes.edit(
                embed=Embed(
                    color=self.bot.yes_color,
                    description=f"{self.bot.yes} {ctx.author.mention}: Succesfully configured the VoiceMaster module",
                )
            )

    @voicemaster.command(name="unsetup", brief="administrator")
    @has_guild_permissions(administrator=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def vm_unsetup(self, ctx: PretendContext):
        """
        Remove the voicemaster module
        """

        async with self.locks[ctx.guild.id]:
            check = await self.bot.db.fetchrow(
                "SELECT * FROM voicemaster WHERE guild_id = $1", ctx.guild.id
            )
            if not check:
                return await ctx.send_warning("VoiceMaster is **not** configured")

            mes = await ctx.send(
                embed=Embed(
                    color=self.bot.color,
                    description=f"{ctx.author.mention}: Disabling the VoiceMaster interface",
                )
            )

            voice = ctx.guild.get_channel(check["channel_id"])
            if voice:
                for channel in voice.category.channels:
                    if channel:
                        await channel.delete(
                            reason=f"VoiceMaster module disabled by {ctx.author}"
                        )
                await voice.category.delete(
                    reason=f"VoiceMaster module disabled by {ctx.author}"
                )

            await self.bot.db.execute(
                "DELETE FROM voicemaster WHERE guild_id = $1", ctx.guild.id
            )
            await self.bot.db.execute(
                "DELETE FROM vm_buttons WHERE guild_id = $1", ctx.guild.id
            )
            return await mes.edit(
                embed=Embed(
                    color=self.bot.yes_color,
                    description=f"{self.bot.yes} {ctx.author.mention}: Succesfully disabled the VoiceMaster module",
                )
            )

    @command(brief="administrator")
    @has_guild_permissions(administrator=True)
    async def interface(self, ctx: PretendContext, *, code: str = None):
        """
        Create a custom voice master interface
        """

        await self.bot.db.execute(
            "DELETE FROM vm_buttons WHERE guild_id = $1", ctx.guild.id
        )
        view = VoiceMasterView(self.bot)
        if not code:
            embed = (
                Embed(
                    color=self.bot.color,
                    title="VoiceMaster Interface",
                    description=f"Control the voice channels created by the bot",
                )
                .set_author(name=ctx.guild.name, icon_url=ctx.guild.icon)
                .set_thumbnail(url=self.bot.user.display_avatar.url)
                .set_footer(text="pretend")
                .add_field(
                    name="usage",
                    value="\n".join(f"{x[0]} - {x[1]}" for x in self.values),
                )
            )
            await view.add_default_buttons(ctx.guild)
            return await ctx.send(embed=embed, view=view)

        items = ButtonScript.script(EmbedBuilder().embed_replacement(ctx.author, code))

        if len(items[2]) == 0:
            await view.add_default_buttons(ctx.guild)
        else:
            for item in items[2]:
                await view.add_button(
                    ctx.guild, item[0], label=item[1], emoji=item[2], style=item[3]
                )

        await ctx.send(content=items[0], embed=items[1], view=view)

    @hybrid_group(aliases=["vc"], invoke_without_command=True)
    async def voice(self, ctx):
        """
        Manage your voice channel using commands
        """

        await ctx.create_pages()

    @voice.command(brief="vc owner")
    @check_vc_owner()
    @bot_has_guild_permissions(manage_channels=True)
    async def lock(self, ctx: PretendContext):
        """
        Lock the voice channel
        """

        overwrite = ctx.author.voice.channel.overwrites_for(ctx.guild.default_role)
        overwrite.connect = False
        await ctx.author.voice.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrite,
            reason=f"Channel locked by {ctx.author}",
        )
        return await ctx.send_success(f"locked <#{ctx.author.voice.channel.id}>")

    @voice.command(help="config", brief="vc owner")
    @check_vc_owner()
    @bot_has_guild_permissions(manage_channels=True)
    async def unlock(self, ctx: PretendContext):
        """
        Unlock the voice channel
        """

        overwrite = ctx.author.voice.channel.overwrites_for(ctx.guild.default_role)
        overwrite.connect = True
        await ctx.author.voice.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrite,
            reason=f"Channel unlocked by {ctx.author}",
        )
        return await ctx.send_success(f"Unlocked <#{ctx.author.voice.channel.id}>")

    @voice.command(brief="vc owner")
    @check_vc_owner()
    @rename_cooldown()
    @bot_has_guild_permissions(manage_channels=True)
    async def rename(self, ctx: PretendContext, *, name: str):
        """
        Rename the voice channel
        """

        await ctx.author.voice.channel.edit(name=name)
        return await ctx.send_success(f"Renamed the voice channel to **{name}**")

    @voice.command(brief="vc owner")
    @check_vc_owner()
    @bot_has_guild_permissions(manage_channels=True)
    async def hide(self, ctx: PretendContext):
        """
        Hide the voice channel
        """

        overwrite = ctx.author.voice.channel.overwrites_for(ctx.guild.default_role)
        overwrite.view_channel = False
        await ctx.author.voice.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrite,
            reason=f"Channel hidden by {ctx.author}",
        )
        return await ctx.send_success(f"Hidden <#{ctx.author.voice.channel.id}>")

    @voice.command(brief="vc owner")
    @check_vc_owner()
    @bot_has_guild_permissions(manage_channels=True)
    async def reveal(self, ctx: PretendContext):
        """
        Reveal the voice channel
        """

        overwrite = ctx.author.voice.channel.overwrites_for(ctx.guild.default_role)
        overwrite.view_channel = True
        await ctx.author.voice.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrite,
            reason=f"Channel revealed by {ctx.author}",
        )
        return await ctx.send_success(f"Revealed <#{ctx.author.voice.channel.id}>")

    @voice.command(brief="vc owner")
    @check_vc_owner()
    @bot_has_guild_permissions(manage_channels=True)
    async def permit(self, ctx: PretendContext, *, member: Member):
        """
        let someone join your locked voice channel
        """

        await ctx.author.voice.channel.set_permissions(member, connect=True)
        return await ctx.send_success(
            f"{member.mention} is allowed to join <#{ctx.author.voice.channel.id}>"
        )

    @voice.command(brief="vc owner")
    @check_vc_owner()
    @bot_has_guild_permissions(manage_channels=True)
    async def reject(self, ctx: PretendContext, *, member: Member):
        """
        Restrict someone from joining your voice channel
        """

        if member.id == ctx.author.id:
            return await ctx.reply("why would u wanna kick urself >_<")

        if member in ctx.author.voice.channel.members:
            await member.move_to(channel=None)

        await ctx.author.voice.channel.set_permissions(member, connect=False)
        return await ctx.send_success(
            f"{member.mention} is not allowed to join <#{ctx.author.voice.channel.id}> anymore"
        )

    @voice.command(brief="vc owner")
    @check_vc_owner()
    @bot_has_guild_permissions(manage_channels=True)
    async def kick(self, ctx: PretendContext, *, member: Member):
        """
        Kick a membert from your voice channel
        """

        if member.id == ctx.author.id:
            return await ctx.reply("why would u wanna kick urself >_<")

        if not member in ctx.author.voice.channel.members:
            return await ctx.send_error(
                f"{member.mention} isn't in **your** voice channel"
            )

        await member.move_to(channel=None)
        return await ctx.send_success(
            f"{member.mention} got kicked from <#{ctx.author.voice.channel.id}>"
        )

    @voice.command(help="config")
    async def claim(self, ctx: PretendContext):
        """
        Claim the voice channel ownership
        """

        if not ctx.author.voice:
            return await ctx.send_warning("You are **not** in a voice channel")

        check = await self.bot.db.fetchrow(
            "SELECT user_id FROM vcs WHERE voice = $1", ctx.author.voice.channel.id
        )

        if not check:
            return await ctx.send_warning(
                "You are **not** in a voice channel made by the bot"
            )

        if ctx.author.id == check[0]:
            return await ctx.send_warning("You are the **owner** of this voice channel")

        if check[0] in [m.id for m in ctx.author.voice.channel.members]:
            return await ctx.send_warning("The owner is still in the voice channel")

        await self.bot.db.execute(
            "UPDATE vcs SET user_id = $1 WHERE voice = $2",
            ctx.author.id,
            ctx.author.voice.channel.id,
        )
        return await ctx.send_success("**You** are the new owner of this voice channel")

    @voice.command(brief="vc owner")
    @check_vc_owner()
    async def transfer(self, ctx: PretendContext, *, member: Member):
        """
        Transfer the voice channel ownership to another member
        """

        if not member in ctx.author.voice.channel.members:
            return await ctx.send_warning(
                f"{member.mention} is not in your voice channel"
            )

        if member == ctx.author:
            return await ctx.send_warning(
                "You are already the **owner** of this **voice channel**"
            )

        await self.bot.db.execute(
            "UPDATE vcs SET user_id = $1 WHERE voice = $2",
            member.id,
            ctx.author.voice.channel.id,
        )
        return await ctx.send_success(
            f"Transfered the voice ownership to {member.mention}"
        )


async def setup(bot) -> None:
    await bot.add_cog(Voicemaster(bot))
