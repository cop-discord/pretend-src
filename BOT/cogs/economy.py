import random
import asyncio
import discord
import datetime
import humanize

from collections import defaultdict
from discord.ext.commands import (
    Cog,
    hybrid_command,
    command,
    Author,
    cooldown,
    BucketType,
    CommandError,
    CommandOnCooldown,
)

from tools.bot import Pretend
from tools.misc.views import Transfer
from tools.helpers import PretendContext
from tools.converters import CashAmount, CardAmount, EligibleEconomyMember
from tools.predicates import create_account, daily_taken, dice_cooldown


class Economy(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.emoji = "🏦"
        self.description = "Economy commands"
        self.cash = "💵"
        self.card = "💳"
        self.color = 0xD3D3D3
        self.locks = defaultdict(asyncio.Lock)
        self.jobs = self.load_jobs()

    def load_jobs(self):
        """
        Load the job options
        """

        with open("./texts/jobs.txt") as f:
            return f.read().splitlines()

    def humanize_number(self, number: float):
        """
        Convert big float
        """

        if number < 9999999999:
            return f"{number:,}"

        digits = len(str(int(number))) - 10
        return f"{str(int(number))[:10]}... (+ {digits} more)"

    @hybrid_command()
    @create_account()
    async def transfer(
        self, ctx: PretendContext, amount: CashAmount, *, member: EligibleEconomyMember
    ):
        """
        Transfer cash to a member
        """

        embed = discord.Embed(
            color=self.color,
            description=f"{self.emoji} {ctx.author.mention} are you sure you want to transfer **{amount}** {self.cash} to {member.mention}",
        )
        view = Transfer(ctx, member, amount)
        view.message = await ctx.send(embed=embed, view=view)

    @command(aliases=["gamble"])
    @create_account()
    @dice_cooldown()
    async def dice(self, ctx: PretendContext, amount: CashAmount):
        """
        Play a dice game
        """

        async with self.locks[ctx.author.id]:
            check = await self.bot.db.fetchrow(
                "SELECT * FROM economy WHERE user_id = $1", ctx.author.id
            )
            cash = check["cash"]

            if cash < amount:
                return await ctx.send_error("You do not have enough money to dice")

            if amount < 20:
                return await ctx.send_error(
                    f"You cannot bet less than **20** {self.card}"
                )

            user_dice = random.randint(1, 6) + random.randint(1, 6)
            bot_dice = random.randint(1, 6) + random.randint(1, 6)
            if user_dice > bot_dice:
                await ctx.send(f"You won **{amount}** {self.cash}")
                await self.bot.db.execute(
                    """
         UPDATE economy
         SET cash = $1,
         dice = $2
         WHERE user_id = $3
         """,
                    round(cash + amount, 2),
                    int(
                        (
                            datetime.datetime.now() + datetime.timedelta(seconds=10)
                        ).timestamp()
                    ),
                    ctx.author.id,
                )
            elif bot_dice > user_dice:
                await ctx.send(f"You lost **{amount}** {self.cash}")
                await self.bot.db.execute(
                    """
         UPDATE economy 
         SET cash = $1,
         dice = $2
         WHERE user_id = $3
         """,
                    round(cash - amount, 2),
                    int(
                        (
                            datetime.datetime.now() + datetime.timedelta(seconds=10)
                        ).timestamp()
                    ),
                    ctx.author.id,
                )
            else:
                await ctx.send("It's a tie")
                await self.bot.db.execute(
                    """
          UPDATE economy 
          SET dice = $1
          WHERE user_id = $2
          """,
                    int(
                        (
                            datetime.datetime.now() + datetime.timedelta(seconds=10)
                        ).timestamp()
                    ),
                    ctx.author.id,
                )

    @hybrid_command()
    @create_account()
    @daily_taken()
    async def daily(self, ctx: PretendContext):
        """
        Claim your daily cash
        """

        async with self.locks[ctx.author.id]:
            check = await self.bot.db.fetchrow(
                "SELECT * FROM economy WHERE user_id = $1", ctx.author.id
            )
            donor = await self.bot.db.fetchrow(
                "SELECT * FROM donor WHERE user_id = $1", ctx.author.id
            )
            newcash = round(random.uniform(1000, 2000), 2)

            if donor:
                newcash += round((20 / 100) * newcash, 2)

            newclaim = int(
                (datetime.datetime.now() + datetime.timedelta(days=1)).timestamp()
            )
            await self.bot.db.execute(
                """
        UPDATE economy
        SET cash = $1,
        daily = $2
        WHERE user_id = $3
        """,
                round(check["cash"] + newcash, 2),
                newclaim,
                ctx.author.id,
            )
            return await ctx.economy_send(
                f"You have claimed **{round(newcash, 2)}** {self.cash} {'+20%' if donor else ''}\nCome back **tomorrow** to claim again"
            )

    @hybrid_command()
    @create_account()
    async def withdraw(self, ctx: PretendContext, amount: CardAmount):
        """
        withdraw card money to cash
        """

        async with self.locks[ctx.author.id]:
            check = await self.bot.db.fetchrow(
                "SELECT * FROM economy WHERE user_id = $1", ctx.author.id
            )
            card = check["card"]

            if card < amount:
                return await ctx.send_error("You do not have enough money to withdraw")

            await self.bot.db.execute(
                """
        UPDATE economy 
        SET cash = $1, 
        card = $2 
        WHERE user_id = $3
        """,
                round(check["cash"] + amount, 2),
                round(card - amount, 2),
                ctx.author.id,
            )
            return await ctx.economy_send(
                f"Withdrawed **{self.humanize_number(amount)}** {self.card}"
            )

    @hybrid_command(aliases=["dep"])
    @create_account()
    async def deposit(self, ctx: PretendContext, amount: CashAmount):
        """
        Deposit cash to card
        """

        async with self.locks[ctx.author.id]:
            check = await self.bot.db.fetchrow(
                "SELECT * FROM economy WHERE user_id = $1", ctx.author.id
            )
            cash = check["cash"]

            if cash < amount:
                return await ctx.send_error("You do not have enough money to deposit")

            await self.bot.db.execute(
                """
      UPDATE economy 
      SET cash = $1, 
      card = $2 
      WHERE user_id = $3
      """,
                round(cash - amount, 2),
                round(check["card"] + amount, 2),
                ctx.author.id,
            )
            return await ctx.economy_send(
                f"Deposited **{self.humanize_number(amount)}** {self.cash}"
            )

    @hybrid_command()
    @create_account()
    async def coinflip(self, ctx: PretendContext, amount: CashAmount, bet: str):
        """
        Play a coinflip game
        """

        async with self.locks[ctx.author.id]:
            cash = await self.bot.db.fetchval(
                "SELECT cash FROM economy WHERE user_id = $1", ctx.author.id
            )

            if amount < 20:
                return await ctx.send_error(
                    f"You cannot bet less than **20** {self.cash}"
                )

            if cash < amount:
                return await ctx.send_error("Not enough money to gamble")

            if not bet.lower() in ["heads", "tails"]:
                return await ctx.send_warning(
                    "You can only bet on **heads** or **tails**"
                )

            embed = discord.Embed(
                color=self.bot.color,
                description=f":coin: {ctx.author.mention} Flipping the coin....",
            )

            mes = await ctx.reply(embed=embed)
            response = random.choice(["heads", "tails"])

            if response == bet.lower():
                e = discord.Embed(
                    color=self.bot.yes_color,
                    description=f"It's **{response}**\nYou won **{self.humanize_number(amount)}** {self.cash}",
                )

                await mes.edit(embed=e)
                await self.bot.db.execute(
                    """
          UPDATE economy
          SET cash = $1
          WHERE user_id = $2
          """,
                    round(cash + amount, 2),
                    ctx.author.id,
                )
            else:
                e = discord.Embed(
                    color=self.bot.no_color,
                    description=f"You chose **{bet.lower()}**, but it's **{response}**\nYou lost **{self.humanize_number(amount)}** {self.cash}",
                )

                await mes.edit(embed=e)
                await self.bot.db.execute(
                    """
          UPDATE economy
          SET cash = $1
          WHERE user_id = $2
          """,
                    round(cash - amount, 2),
                    ctx.author.id,
                )

    @hybrid_command()
    @create_account()
    @cooldown(1, 20, BucketType.user)
    async def work(self, ctx: PretendContext):
        """
        Work a job and earn money
        """

        cash = await self.bot.db.fetchval(
            "SELECT cash FROM economy WHERE user_id = $1", ctx.author.id
        )
        received = round(random.uniform(50, 300), 2)
        new_cash = round(cash + received, 2)
        await self.bot.db.execute(
            "UPDATE economy SET cash = $1 WHERE user_id = $2", new_cash, ctx.author.id
        )
        await ctx.economy_send(
            f"You were working as **a {random.choice(self.jobs)}** and got **{received}** {self.cash}"
        )

    @work.error
    async def on_command_error(self, ctx: PretendContext, error: CommandError):
        if isinstance(error, CommandOnCooldown):
            return await ctx.economy_send(
                f"You have to wait **{humanize.precisedelta(datetime.timedelta(seconds=error.retry_after), format='%0.0f')}** to work again"
            )

    @hybrid_command(aliases=["lb"])
    async def leaderboard(self, ctx: PretendContext):
        """
        Global leaderboard for economy
        """

        results = await self.bot.db.fetch("SELECT * FROM economy")
        sorted_results = sorted(
            results, key=lambda c: c["cash"] + c["card"], reverse=True
        )

        to_show = [
            f"{self.bot.get_user(check['user_id'])} - {self.humanize_number(round(check['cash']+check['card'], 2))} {self.cash}"
            for check in sorted_results
            if self.bot.get_user(check["user_id"])
        ][:50]

        await ctx.paginate(
            to_show,
            f"Economy leaderboard",
            {"name": ctx.author, "icon_url": ctx.author.display_avatar},
        )

    @hybrid_command()
    async def reset(self, ctx: PretendContext):
        """
        Close your economy account
        """

        if check := await self.bot.db.fetchrow(
            "SELECT * FROM economy WHERE user_id = $1", ctx.author.id
        ):

            async def yes_callback(interaction: discord.Interaction):
                await interaction.client.db.execute(
                    "DELETE FROM economy WHERE user_id = $1", interaction.user.id
                )
                embed = discord.Embed(
                    color=interaction.client.yes_color,
                    description=f"{interaction.user.mention}: Closed your **economy** account",
                )

                await interaction.response.edit_message(embed=embed, view=None)

            async def no_callback(interaction: discord.Interaction):
                embed = discord.Embed(
                    color=interaction.client.color, description=f"Cancelling action..."
                )

                await interaction.response.edit_message(embed=embed, view=None)

            await ctx.confirmation_send(
                f"Are you sure you want to **close** your economy account?\nYou will lose a total of **{self.humanize_number(check['cash'])}** {self.cash} and **{self.humanize_number(check['card'])}** {self.card}",
                yes_callback,
                no_callback,
            )
        else:
            return await ctx.send_error("You do **not** have an economy account opened")

    @hybrid_command(aliases=["bal"])
    @create_account()
    async def balance(self, ctx: PretendContext, *, member: discord.Member = Author):
        """
        Check someone's balance
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM economy WHERE user_id = $1", member.id
        )

        if not check:
            return await ctx.send_error(
                f"Member doesn't have any **credits** {self.cash}"
            )

        daily = "Available"
        if check["daily"]:
            if datetime.datetime.now().timestamp() < check["daily"]:
                daily = self.bot.humanize_date(
                    datetime.datetime.fromtimestamp(check["daily"])
                )

        embed = discord.Embed(color=self.color)
        embed.set_author(
            name=f"{member.name}'s balance", icon_url=member.display_avatar.url
        )
        embed.add_field(
            name=f"{self.cash} Cash",
            value=self.humanize_number(check["cash"]),
            inline=False,
        )
        embed.add_field(
            name=f"{self.emoji} Card",
            value=self.humanize_number(check["card"]),
            inline=False,
        )
        embed.add_field(name="💰 Daily", value=daily, inline=False)
        await ctx.send(embed=embed)


async def setup(bot: Pretend) -> None:
    await bot.add_cog(Economy(bot))
