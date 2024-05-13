import re
import json

from discord.ext.commands import Cog, group, has_guild_permissions, Flag

from tools.bot import Pretend
from tools.helpers import PretendContext
from tools.helpers import PretendFlags


class AutoresponderFlags(PretendFlags):
    not_strict: bool = Flag(default=False)


class Responders(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Message triggered response commands"

    @group(invoke_without_command=True)
    async def autoreact(self, ctx):
        await ctx.create_pages()

    @autoreact.command(
        name="add", brief="manage server", usage="example: ;autoreact add skull, 💀"
    )
    @has_guild_permissions(manage_guild=True)
    async def autoreact_add(self, ctx: PretendContext, *, content: str):
        """create an autoreact using a trigger for this server"""
        con = content.split(", ")
        if len(con) == 1:
            return await ctx.send_warning(
                "No reactions found. Make sure to use a `,` to split the trigger from the reactions"
            )

        trigger = con[0].strip()
        if trigger == "":
            return await ctx.send_warning("No trigger found")

        custom_regex = re.compile(r"(<a?)?:\w+:(\d{18}>)?")
        unicode_regex = re.compile(
            "["
            "\U0001F1E0-\U0001F1FF"
            "\U0001F300-\U0001F5FF"
            "\U0001F600-\U0001F64F"
            "\U0001F680-\U0001F6FF"
            "\U0001F700-\U0001F77F"
            "\U0001F780-\U0001F7FF"
            "\U0001F800-\U0001F8FF"
            "\U0001F900-\U0001F9FF"
            "\U0001FA00-\U0001FA6F"
            "\U0001FA70-\U0001FAFF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+"
        )
        reactions = [
            c.strip()
            for c in con[1].split(" ")
            if custom_regex.match(c) or unicode_regex.match(c)
        ]

        if len(reactions) == 0:
            return await ctx.send_error("No emojis found")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM autoreact WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id,
            trigger,
        )

        if not check:
            await self.bot.db.execute(
                "INSERT INTO autoreact VALUES ($1,$2,$3)",
                ctx.guild.id,
                trigger,
                json.dumps(reactions),
            )
        else:
            await self.bot.db.execute(
                "UPDATE autoreact SET reactions = $1 WHERE guild_id = $2 AND trigger = $3",
                json.dumps(reactions),
                ctx.guild.id,
                trigger,
            )

        return await ctx.send_success(
            f"Your autoreact for **{trigger}** has been created with the reactions {' '.join(reactions)}"
        )

    @autoreact.command(name="remove", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def autoreact_remove(self, ctx: PretendContext, *, trigger: str):
        """remove an autoreact"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM autoreact WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id,
            trigger,
        )

        if not check:
            return await ctx.send_warning("There is no **autoreact** with this trigger")

        await self.bot.db.execute(
            "DELETE FROM autoreact WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id,
            trigger,
        )
        return await ctx.send_success(f"Removed **{trigger}** from autoreact")

    @autoreact.command(name="list")
    async def autoreact_list(self, ctx: PretendContext):
        """returns all the autoreactions in the server"""
        check = await self.bot.db.fetch(
            "SELECT * FROM autoreact WHERE guild_id = $1", ctx.guild.id
        )
        if not check:
            return await ctx.send_error(
                "There are no autoreactions available in this server"
            )

        return await ctx.paginate(
            [f"{r['trigger']} - {' '.join(json.loads(r['reactions']))}" for r in check],
            f"Autoreactions ({len(check)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @group(name="autoresponder", aliases=["ar"], invoke_without_command=True)
    async def autoresponder(self, ctx: PretendContext):
        await ctx.create_pages()

    @autoresponder.command(
        name="add",
        brief="manage server",
        usage="example: ;autoresponder add hello, hello world",
    )
    @has_guild_permissions(manage_guild=True)
    async def ar_add(self, ctx: PretendContext, *, response: str):
        """add an autoresponder to the server"""
        responses = response.split(", ", maxsplit=1)
        if len(responses) == 1:
            return await ctx.send_warning(
                "Response not found! Please use `,` to split the trigger and the response"
            )

        trigger = responses[0].strip()

        if trigger == "":
            return await ctx.send_warning("No trigger found")

        resp = responses[1].strip()

        if resp.endswith(" --not_strict"):
            strict = False
        else:
            strict = True

        resp = resp.replace(" --not_strict", "")
        if not response:
            return await ctx.send_warning(
                "Response not found! Please use `,` to split the trigger and the response"
            )

        check = await self.bot.db.fetchrow(
            "SELECT * FROM autoresponder WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id,
            trigger.lower(),
        )
        if check:
            return await ctx.send_warning(
                f"An autoresponder for **{trigger}** already exists"
            )
        else:
            await self.bot.db.execute(
                "INSERT INTO autoresponder VALUES ($1,$2,$3, $4)",
                ctx.guild.id,
                trigger.lower(),
                resp.lower(),
                strict,
            )

        return await ctx.send_success(
            f"Added autoresponder for **{trigger}** - {resp} {'(not strict)' if strict is False else ''}"
        )

    @autoresponder.command(name="remove", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def ar_remove(self, ctx: PretendContext, *, trigger: str):
        """remove an autoresponder from the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM autoresponder WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id,
            trigger,
        )

        if not check:
            return await ctx.send_error(
                "There is no autoresponder with the trigger you have provided"
            )

        await self.bot.db.execute(
            "DELETE FROM autoresponder WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id,
            trigger,
        )
        return await ctx.send_success(f"Deleted the autoresponder for **{trigger}**")

    @autoresponder.command(name="list")
    async def ar_list(self, ctx: PretendContext):
        """returns a list of all autoresponders in the server"""
        results = await self.bot.db.fetch(
            "SELECT * FROM autoresponder WHERE guild_id = $1", ctx.guild.id
        )

        if not results:
            return await ctx.send_warning(f"No **autoresponders** are set!")

        return await ctx.paginate(
            [f"{result['trigger']} - {result['response']}" for result in results],
            f"Autoresponders ({len(results)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Responders(bot))
