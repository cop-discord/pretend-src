import random
import discord
import asyncio
import orjson
import humanize
import datetime

from discord import (
    Interaction,
    ButtonStyle,
    Embed,
    Member,
    TextChannel,
    User,
    Message,
    AllowedMentions,
    File,
)
from discord.ui import Button, View, button

from discord.ext.commands import (
    BadArgument,
    Cog,
    hybrid_command,
    hybrid_group,
    Author,
    command,
    is_owner,
)

from typing import List
from aiogtts import aiogTTS

from tools.bot import Pretend
from tools.helpers import PretendContext

from tools.converters import AbleToMarry
from tools.helpers import PretendContext
from tools.misc.views import MarryView


class TicTacToeButton(Button["TicTacToe"]):
    def __init__(self, x: int, y: int, player1: Member, player2: Member):
        super().__init__(style=ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x
        self.y = y
        self.player1 = player1
        self.player2 = player2

    async def callback(self, interaction: Interaction):
        assert self.view is not None
        view: TicTacToe = self.view
        state = view.board[self.y][self.x]
        if state in (view.X, view.O):
            return

        if view.current_player == view.X:
            if interaction.user != self.player1:
                return await interaction.response.send_message(
                    "You cannot interact with this button", ephemeral=True
                )
            self.style = ButtonStyle.danger
            self.label = "X"
            self.disabled = True
            view.board[self.y][self.x] = view.X
            view.current_player = view.O
            content = f"{self.player1} ⚔️ {self.player2}\n\nIt's **{self.player2.name}**'s turn"
        else:
            if interaction.user != self.player2:
                return await interaction.response.send_message(
                    "You cannot interact with this button", ephemeral=True
                )

            self.style = ButtonStyle.success
            self.label = "O"
            self.disabled = True
            view.board[self.y][self.x] = view.O
            view.current_player = view.X
            content = f"{self.player1} ⚔️ {self.player2}\n\nIt's **{self.player1.name}'s** turn"

        winner = view.check_board_winner()
        if winner is not None:
            if winner == view.X:
                content = f"**{self.player1.name}** won!"

                check = await interaction.client.db.fetchrow(
                    """
                SELECT * FROM gamestats
                WHERE user_id = $1
                AND game = $2
                """,
                    self.player1.id,
                    "tictactoe",
                )

                if not check:
                    await interaction.client.db.execute(
                        """
                INSERT INTO gamestats
                VALUES ($1,$2,$3,$4,$5)
                """,
                        self.player1.id,
                        "tictactoe",
                        1,
                        0,
                        1,
                    )
                else:
                    await interaction.client.db.execute(
                        """
                  UPDATE gamestats
                  SET wins = $1,
                  total = $2
                  WHERE user_id = $3
                  AND game = $4
                  """,
                        check["wins"] + 1,
                        check["total"] + 1,
                        self.player1.id,
                        "tictactoe",
                    )

                check2 = await interaction.client.db.fetchrow(
                    """
                SELECT * FROM gamestats 
                WHERE user_id = $1 
                AND game = $2
                """,
                    self.player2.id,
                    "tictactoe",
                )
                if not check2:
                    await interaction.client.db.execute(
                        """
                  INSERT INTO gamestats
                  VALUES ($1,$2,$3,$4,$5)
                  """,
                        self.player2.id,
                        "tictactoe",
                        0,
                        1,
                        1,
                    )
                else:
                    await interaction.client.db.execute(
                        """
                  UPDATE gamestats 
                  SET loses = $1,
                  total = $2
                  WHERE user_id = $3
                  AND game = $4
                  """,
                        check2["loses"] + 1,
                        check2["total"] + 1,
                        self.player2.id,
                        "tictactoe",
                    )

            elif winner == view.O:
                content = f"**{self.player2.name}** won!"

                check = await interaction.client.db.fetchrow(
                    """
                SELECT * FROM gamestats
                WHERE user_id = $1
                AND game = $2
                """,
                    self.player1.id,
                    "tictactoe",
                )
                if not check:
                    await interaction.client.db.execute(
                        """
                INSERT INTO gamestats 
                VALUES ($1,$2,$3,$4,$5)
                """,
                        self.player2.id,
                        "tictactoe",
                        1,
                        0,
                        1,
                    )
                else:
                    await interaction.client.db.execute(
                        """
                  UPDATE gamestats
                  SET wins = $1,
                  total = $2
                  WHERE user_id = $3
                  AND game = $4
                  """,
                        check["wins"] + 1,
                        check["total"] + 1,
                        self.player2.id,
                        "tictactoe",
                    )

                check2 = await interaction.client.db.fetchrow(
                    """
                SELECT * FROM gamestats 
                WHERE user_id = $1
                AND game = $2
                """,
                    self.player1.id,
                    "tictactoe",
                )
                if not check2:
                    await interaction.client.db.execute(
                        """
                  INSERT INTO gamestats
                  VALUES ($1,$2,$3,$4,$5)
                  """,
                        self.player1.id,
                        "tictactoe",
                        0,
                        1,
                        1,
                    )
                else:
                    await interaction.client.db.execute(
                        """
                  UPDATE gamestats 
                  SET loses = $1,
                  total = $2
                  WHERE user_id = $3
                  AND game = $4
                  """,
                        check2["loses"] + 1,
                        check2["total"] + 1,
                        self.player1.id,
                        "tictactoe",
                    )

            else:
                content = "It's a tie!"
                for i in [self.player1.id, self.player2.id]:
                    check = await interaction.client.db.fetchrow(
                        """
                    SELECT * FROM gamestats 
                    WHERE user_id = $1
                    AND game = $2
                    """,
                        i,
                        "tictactoe",
                    )
                    if not check:
                        await interaction.client.db.execute(
                            """
                      INSERT INTO gamestats
                      VALUES ($1,$2,$3,$4,$5)
                      """,
                            i,
                            "tictactoe",
                            0,
                            0,
                            1,
                        )
                    else:
                        await interaction.client.db.execute(
                            """
                      UPDATE gamestats 
                      SET total = $1
                      WHERE user_id = $2
                      AND game = $3
                      """,
                            check["total"] + 1,
                            i,
                            "tictactoe",
                        )

            for child in view.children:
                child.disabled = True

            view.stop()

        await interaction.response.edit_message(content=content, view=view)


class TicTacToe(View):
    children: List[TicTacToeButton]
    X = -1
    O = 1
    Tie = 2

    def __init__(self, player1: Member, player2: Member):
        super().__init__()
        self.current_player = self.X
        self.board = [
            [0, 0, 0],
            [0, 0, 0],
            [0, 0, 0],
        ]

        for x in range(3):
            for y in range(3):
                self.add_item(TicTacToeButton(x, y, player1, player2))

    def check_board_winner(self):
        for across in self.board:
            value = sum(across)
            if value == 3:
                return self.O
            elif value == -3:
                return self.X

        for line in range(3):
            value = self.board[0][line] + self.board[1][line] + self.board[2][line]
            if value == 3:
                return self.O
            elif value == -3:
                return self.X

        diag = self.board[0][2] + self.board[1][1] + self.board[2][0]
        if diag == 3:
            return self.O
        elif diag == -3:
            return self.X

        diag = self.board[0][0] + self.board[1][1] + self.board[2][2]
        if diag == 3:
            return self.O
        elif diag == -3:
            return self.X

        if all(i != 0 for row in self.board for i in row):
            return self.Tie

        return None


class RockPaperScissors(View):
    def __init__(self, ctx: PretendContext):
        self.ctx = ctx
        self.get_emoji = {"rock": "🪨", "paper": "📰", "scissors": "✂️"}
        self.status = False
        super().__init__(timeout=10)

    async def disable_buttons(self):
        await self.message.edit(view=None)

    async def interaction_check(self, interaction: Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.warn("This is **not** your game")
        return interaction.user.id == self.ctx.author.id

    async def action(self, interaction: Interaction, selection: str):
        botselection = random.choice(["rock", "paper, scissors"])

        def getwinner():
            if botselection == "rock" and selection == "scissors":
                return interaction.client.user.id
            elif botselection == "rock" and selection == "paper":
                return interaction.user.id
            elif botselection == "paper" and selection == "rock":
                return interaction.client.user.id
            elif botselection == "paper" and selection == "scissors":
                return interaction.user.id
            elif botselection == "scissors" and selection == "rock":
                return interaction.user.id
            elif botselection == "scissors" and selection == "paper":
                return interaction.client.user.id
            else:
                return "tie"

        if getwinner() == "tie":
            check = await interaction.client.db.fetchrow(
                """
        SELECT * FROM gamestats 
        WHERE user_id = $1
        AND game = $2
        """,
                interaction.user.id,
                "rockpaperscissors",
            )
            if not check:
                await interaction.client.db.execute(
                    """
          INSERT INTO gamestats 
          VALUES ($1,$2,$3,$4,$5)
          """,
                    interaction.user.id,
                    "rockpaperscissors",
                    0,
                    0,
                    1,
                )
            else:
                await interaction.client.db.execute(
                    """
          UPDATE gamestats 
          SET total = $1
          WHERE user_id = $2
          AND game = $3
          """,
                    check["total"] + 1,
                    interaction.user.id,
                    "rockpaperscissors",
                )

            await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.color,
                    title="Tie!",
                    description=f"You both picked {self.get_emoji.get(selection)}",
                )
            )
        elif getwinner() == interaction.user.id:
            check = await interaction.client.db.fetchrow(
                """
        SELECT * FROM gamestats 
        WHERE user_id = $1
        AND game = $2
        """,
                interaction.user.id,
                "rockpaperscissors",
            )
            if not check:
                await interaction.client.db.execute(
                    """
          INSERT INTO gamestats 
          VALUES ($1,$2,$3,$4,$5)
          """,
                    interaction.user.id,
                    "rockpaperscissors",
                    1,
                    0,
                    1,
                )
            else:
                await interaction.client.db.execute(
                    """
          UPDATE gamestats
          SET wins = $1, 
          total = $2
          WHERE user_id = $3
          AND game = $4
          """,
                    check["wins"] + 1,
                    check["total"] + 1,
                    interaction.user.id,
                    "rockpaperscissors",
                )

            await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.color,
                    title="You won!",
                    description=f"You picked {self.get_emoji.get(selection)} and the bot picked {self.get_emoji.get(botselection)}",
                )
            )
        else:
            check = await interaction.client.db.fetchrow(
                """
        SELECT * FROM gamestats
        WHERE user_id = $1 
        AND game = $2
        """,
                interaction.user.id,
                "rockpaperscissors",
            )
            if not check:
                await interaction.client.db.execute(
                    """
          INSERT INTO gamestats 
          VALUES ($1,$2,$3,$4,$5)
          """,
                    interaction.user.id,
                    "rockpaperscissors",
                    0,
                    1,
                    1,
                )
            else:
                await interaction.client.db.execute(
                    """
          UPDATE gamestats 
          SET loses = $1, 
          total = $2 
          WHERE user_id = $3 
          AND game = $4
          """,
                    check["loses"] + 1,
                    check["total"] + 1,
                    interaction.user.id,
                    "rockpaperscissors",
                )

            await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.color,
                    title="Bot won!",
                    description=f"You picked {self.get_emoji.get(selection)} and the bot picked {self.get_emoji.get(botselection)}",
                )
            )

        await self.disable_buttons()
        self.status = True

    @button(emoji="🪨")
    async def rock(self, interaction: Interaction, button: Button):
        return await self.action(interaction, "rock")

    @button(emoji="📰")
    async def paper(self, interaction: Interaction, button: Button):
        return await self.action(interaction, "paper")

    @button(emoji="✂️")
    async def scissors(self, interaction: Interaction, button: Button):
        return await self.action(interaction, "scissors")

    async def on_timeout(self):
        if self.status == False:
            await self.disable_buttons()


class BlackTea:
    def __init__(self, bot):
        self.bot = bot
        self.color = 0xA5D287
        self.emoji = "🍵"
        self.MatchStart = []
        self.lifes = {}
        self.players = {}

    def get_string(self):
        words = self.get_words()
        word = random.choice([l for l in words if len(l) > 3])
        return word[:3]

    async def send_embed(self, channel: TextChannel, content: str):
        return await channel.send(embed=Embed(color=self.color, description=content))

    async def lost_a_life(self, member: int, reason: str, channel: TextChannel):
        lifes = self.lifes[f"{channel.guild.id}"].get(f"{member}")
        self.lifes[f"{channel.guild.id}"][f"{member}"] = lifes + 1

        if reason == "timeout":
            await self.send_embed(
                channel,
                f"⏰ <@{member}> time is up! **{3-int(self.lifes[f'{channel.guild.id}'][f'{member}'])}** lifes left..",
            )

        elif reason == "wrong":
            await self.send_embed(
                channel,
                f"💥 <@{member}> wrong answer! **{3-int(self.lifes[f'{channel.guild.id}'][f'{member}'])}** lifes left..",
            )

        if self.lifes[f"{channel.guild.id}"][f"{member}"] == 3:
            await self.send_embed(channel, f"☠️ <@{member}> you're eliminated")
            check = await self.bot.db.fetchrow(
                "SELECT * FROM gamestats WHERE user_id = $1 AND game = $2",
                member,
                "blacktea",
            )

            if not check:
                await self.bot.db.execute(
                    "INSERT INTO gamestats VALUES ($1,$2,$3,$4,$5)",
                    member,
                    "blacktea",
                    0,
                    1,
                    1,
                )
            else:
                await self.bot.db.execute(
                    """
          UPDATE gamestats 
          SET loses = $1,
          total = $2
          WHERE user_id = $3
          AND game = $4
          """,
                    check["loses"] + 1,
                    check["total"] + 1,
                    member,
                    "blacktea",
                )

            del self.lifes[f"{channel.guild.id}"][f"{member}"]
            self.players[f"{channel.guild.id}"].remove(member)
            await self.add_loser(member)

    def match_started(self, guild_id: int):
        if guild_id in self.MatchStart:
            raise BadArgument("A Black Tea match is **already** in progress")
        else:
            self.MatchStart.append(guild_id)

    def get_words(self):
        data = open("./texts/wordlist.txt", encoding="utf-8")
        return [d for d in data.read().splitlines()]

    def clear_all(self):
        self.MatchStart = []
        self.lifes = {}
        self.players = {}

    def remove_stuff(self, guild_id: int):
        del self.players[f"{guild_id}"]
        del self.lifes[f"{guild_id}"]
        self.bot.tea.MatchStart.remove(guild_id)

    async def add_loser(self, player: int):
        check = await self.bot.db.fetchrow(
            "SELECT * FROM gamestats WHERE user_id = $1 AND game = $2",
            player,
            "blacktea",
        )
        if not check:
            return await self.bot.db.execute(
                "INSERT INTO gamestats VALUES ($1,$2,$3,$4,$5)",
                player,
                "blacktea",
                0,
                1,
                1,
            )
        else:
            return await self.bot.db.execute(
                """
        UPDATE gamestats 
        SET loses = $1, 
        total = $2 
        WHERE user_id = $3 
        AND game = $4
        """,
                check["loses"] + 1,
                check["total"] + 1,
                player,
                "blacktea",
            )

    async def add_winner(self, player: int):
        check = await self.bot.db.fetchrow(
            "SELECT * FROM gamestats WHERE user_id = $1 AND game = $2",
            player,
            "blacktea",
        )
        if not check:
            return await self.bot.db.execute(
                "INSERT INTO gamestats VALUES ($1,$2,$3,$4,$5)",
                player,
                "blacktea",
                1,
                0,
                1,
            )
        else:
            return await self.bot.db.execute(
                """
        UPDATE gamestats 
        SET wins = $1, 
        total = $2 
        WHERE user_id = $3 
        AND game = $4
        """,
                check["wins"] + 1,
                check["total"] + 1,
                player,
                "blacktea",
            )


class Fun(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.wedding = "💒"
        self.marry_color = 0xFF819F
        self.description = "Fun commands"
        self.songkey = "348c90f9d1mshf17b25698213ae5p186e51jsn84ed67bb1fe9"

    async def stats_execute(self, ctx: PretendContext, member: User) -> Message:
        """
        Execute any of the stats commands
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM gamestats WHERE game = $1 AND user_id = $2",
            ctx.command.name,
            member.id,
        )

        if not check:
            return await ctx.send_error("There are no stats recorded for this member")

        embed = Embed(
            color=self.bot.color,
            title=f"Stats for {ctx.command.name}",
            description=f"**Wins:** {check['wins']}\n**Loses:** {check['loses']}\n**Matches:** {check['total']}",
        ).set_author(name=member.name, icon_url=member.display_avatar.url)

        return await ctx.reply(embed=embed)

    def shorten(self, value: str, length: int = 32):
        if len(value) > length:
            value = value[: length - 2] + ("..." if len(value) > length else "").strip()
        return value

    @hybrid_command()
    async def quran(self, ctx: PretendContext):
        """
        Get a random quran verse
        """

        result = await self.bot.session.get_json(
            "https://api.alquran.cloud/v1/surah/40/en.sahih"
        )
        name = f"{result['data']['name']} ({result['data']['englishName']})"
        number = result["data"]["number"]
        ayah = random.choice(result["data"]["ayahs"])
        numberInSurah = ayah["numberInSurah"]
        text = ayah["text"]

        embed = Embed(
            color=self.bot.color, description=f"**{number}:{numberInSurah}** {text}"
        ).set_author(name=name)

        return await ctx.send(embed=embed)

    @hybrid_command()
    async def bible(self, ctx: PretendContext):
        """
        Get a random bible verse
        """

        params = {"format": "json", "order": "random"}

        result = await self.bot.session.get_json(
            "https://beta.ourmanna.com/api/v1/get", params=params
        )
        embed = Embed(
            color=self.bot.color, description=result["verse"]["details"]["text"]
        )
        embed.set_author(name=result["verse"]["details"]["reference"])
        await ctx.send(embed=embed)

    @hybrid_command()
    async def blacktea(self, ctx: PretendContext):
        """
        play blacktea with the server members
        """

        BlackTea(self.bot).match_started(ctx.guild.id)
        embed = Embed(color=BlackTea(self.bot).color, title="BlackTea Matchmaking")
        embed.set_thumbnail(
            url="https://cdn.discordapp.com/attachments/1117819522372616352/1118203618978451596/emoji.png"
        )
        embed.add_field(
            name="guide",
            value=f"- React with {BlackTea(self.bot).emoji} to join the round\n- You have 20 seconds to join\n- The game starts only if there are at least 2 joined players\n- Everyone has 3 lifes\n- Think about a word that starts with the specific letters given",
        )
        mes = await ctx.send(embed=embed)
        await mes.add_reaction(BlackTea(self.bot).emoji)
        await asyncio.sleep(20)
        try:
            newmes = await ctx.channel.fetch_message(mes.id)
        except:
            BlackTea(self.bot).MatchStart.remove(ctx.guild.id)
            return await ctx.send("The blacktea message was deleted")

        users = [
            u.id async for u in newmes.reactions[0].users() if u.id != self.bot.user.id
        ]

        if len(users) < 2:
            BlackTea(self.bot).MatchStart.remove(ctx.guild.id)
            return await ctx.send(
                "not enough players to start the blacktea match... 😓"
            )

        words = BlackTea(self.bot).get_words()
        BlackTea(self.bot).players.update({f"{ctx.guild.id}": users})
        BlackTea(self.bot).lifes.update(
            {f"{ctx.guild.id}": {f"{user}": 0 for user in users}}
        )

        while len(BlackTea(self.bot).players[f"{ctx.guild.id}"]) > 1:
            for user in users:
                rand = BlackTea(self.bot).get_string()
                await BlackTea(self.bot).send_embed(
                    ctx.channel,
                    f"{BlackTea(self.bot).emoji} <@{user}>: Say a word containing **{rand}** in **10 seconds**",
                )
                try:
                    message = await self.bot.wait_for(
                        "message",
                        check=lambda m: m.channel.id == ctx.channel.id
                        and m.author.id == user,
                        timeout=10,
                    )
                    if rand in message.content and message.content in words:
                        await BlackTea(self.bot).send_embed(
                            ctx.channel,
                            f"<a:happybear:1118213146159624243> <@{user}> Correct answer!",
                        )
                    else:
                        await BlackTea(self.bot).lost_a_life(user, "wrong", ctx.channel)
                except asyncio.TimeoutError:
                    await BlackTea(self.bot).lost_a_life(user, "timeout", ctx.channel)

        await BlackTea(self.bot).add_winner(
            BlackTea(self.bot).players[f"{ctx.guild.id}"][0]
        )
        await BlackTea(self.bot).send_embed(
            ctx.channel,
            f"👑 <@{BlackTea(self.bot).players[f'{ctx.guild.id}'][0]}> Won the game!!",
        )
        member = BlackTea(self.bot).players[str(ctx.guild.id)][0]
        check = await self.bot.db.fetchrow(
            "SELECT * FROM gamestats WHERE user_id = $1 AND game = $2",
            member,
            "blacktea",
        )

        if not check:
            await self.bot.db.execute(
                "INSERT INTO gamestats VALUES ($1,$2,$3,$4,$5)",
                member,
                "blacktea",
                1,
                0,
                1,
            )
        else:
            await self.bot.db.execute(
                """
        UPDATE gamestats SET wins = $1, 
        total = $2 
        WHERE user_id = $3 
        AND game = $4
        """,
                check["wins"] + 1,
                check["total"] + 1,
                member,
                "blacktea",
            )

        self.bot.tea.remove_stuff(ctx.guild.id)

    @hybrid_group(
        invoke_without_command=True,
        description="check a member's stats for a certain game",
    )
    async def stats(self, ctx: PretendContext):
        """
        check a member's stats for a certain game
        """

        await ctx.create_pages()

    @stats.command(name="tictactoe", aliases=["ttt"])
    async def stats_ttt(self, ctx: PretendContext, *, member: User = Author):
        """
        View a member's stats for tictactoe
        """

        await self.stats_execute(ctx, member)

    @stats.command(name="blacktea")
    async def stats_blacktea(self, ctx: PretendContext, *, member: User = Author):
        """
        View a member's stats for blacktea
        """

        await self.stats_execute(ctx, member)

    @stats.command(name="rockpaperscissors", aliases=["rps"])
    async def stats_rps(self, ctx: PretendContext, *, member: User = Author):
        """
        View a member's stats for rockpaperscissors
        """

        await self.stats_execute(ctx, member)

    @command()
    async def pack(self, ctx: PretendContext, *, member: Member):
        """
        Pack a member
        """

        if member == ctx.author:
            return await ctx.reply("Why do you want to pack yourself ://")

        result = await self.bot.session.get_json(
            "https://evilinsult.com/generate_insult.php?lang=en&type=json"
        )
        await ctx.send(
            f"{member.mention} {result['insult']}",
            allowed_mentions=AllowedMentions.none(),
        )

    @hybrid_command(name="8ball")
    async def eightball(self, ctx: PretendContext, *, question: str):
        """
        Ask the 8ball a question
        """

        await ctx.reply(
            f"question: {question}{'?' if not question.endswith('?') else ''}\n{random.choice(['yes', 'no', 'never', 'most likely', 'absolutely', 'absolutely not', 'of course not'])}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @hybrid_command()
    async def bird(self, ctx: PretendContext):
        """
        Send a random bird image
        """

        data = await self.bot.session.get_json("https://api.alexflipnote.dev/birb")
        await ctx.reply(
            file=File(fp=await self.bot.getbyte(data["file"]), filename="bird.png")
        )

    @hybrid_command()
    async def dog(self, ctx: PretendContext):
        """
        Send a random dog image
        """

        data = await self.bot.session.get_json("https://random.dog/woof.json")
        await ctx.reply(
            file=File(
                fp=await self.bot.getbyte(data["url"]),
                filename=f"dog{data['url'][-4:]}",
            )
        )

    @hybrid_command()
    async def cat(self, ctx: PretendContext):
        """
        Send a random cat image
        """

        data = (
            await self.bot.session.get_json(
                "https://api.thecatapi.com/v1/images/search"
            )
        )[0]
        await ctx.reply(
            file=File(fp=await self.bot.getbyte(data["url"]), filename="cat.png")
        )

    @hybrid_command()
    async def capybara(self, ctx: PretendContext):
        """
        Send a random capybara image
        """

        data = await self.bot.session.get_json(
            "https://api.capy.lol/v1/capybara?json=true"
        )
        await ctx.reply(
            file=File(
                fp=await self.bot.getbyte(data["data"]["url"]), filename="cat.png"
            )
        )

    @hybrid_command(aliases=["fact", "uf"])
    async def uselessfact(self, ctx: PretendContext):
        """
        Returns an useless fact
        """

        data = (
            await self.bot.session.get_json(
                "https://uselessfacts.jsph.pl/random.json?language=en"
            )
        )["text"]
        await ctx.reply(data)

    @hybrid_command(aliases=["rps"])
    async def rockpaperscisssors(self, ctx: PretendContext):
        """
        Play rockpapaerscissors
        """

        view = RockPaperScissors(ctx)
        embed = Embed(
            color=self.bot.color,
            title="Rock Paper Scissors!",
            description="Click a button to play!",
        )
        view.message = await ctx.reply(embed=embed, view=view)

    @command(name="choose")
    async def choose_cmd(self, ctx: PretendContext, *, choices: str):
        """
        Choose between options
        """

        if len(choices := choices.split(", ")) == 1:
            return await ctx.send_warning(
                f"Not enough **choices**- seperate your choices with a `,`"
            )

        final = random.choice(choices).strip()
        return await ctx.pretend_send(f"I chose `{final}`")

    @command(name="quickpoll", aliases=["poll"])
    async def quickpoll_cmd(self, ctx: PretendContext, *, question: str):
        """
        Create a poll
        """

        message = await ctx.reply(
            embed=Embed(color=self.bot.color, description=question).set_author(
                name=f"{ctx.author} asked"
            )
        )

        for m in ["👍", "👎"]:
            await message.add_reaction(m)

    @hybrid_command()
    async def ship(self, ctx, member: Member):
        """
        Check the ship rate between you and a member
        """

        return await ctx.reply(
            f"**{ctx.author.name}** 💞 **{member.name}** = **{random.randrange(101)}%**"
        )

    @hybrid_command()
    async def advice(self, ctx: PretendContext):
        """
        Get a random advice
        """

        data = orjson.loads(
            await self.bot.session.get_text("https://api.adviceslip.com/advice")
        )
        return await ctx.reply(data["slip"]["advice"])

    @hybrid_command(name="tictactoe", aliases=["ttt"])
    async def tictactoe(self, ctx: PretendContext, *, member: Member):
        """
        Play tictactoe with a member
        """

        if member.id == ctx.author.id:
            return await ctx.send_warning("You cannot play against yourself")

        if member.bot:
            return await ctx.send_warning("You cannot play against a bot")

        view = TicTacToe(ctx.author, member)
        view.message = await ctx.send(
            content=f"{ctx.author} ⚔️ {member}\n\nIt's {ctx.author.name}'s turn",
            view=view,
        )

    @command(aliases=["tts"])
    async def textospeech(self, ctx: PretendContext, *, message: str):
        """
        Convert your message into audio
        """

        await aiogTTS().save(message, "tts.mp3", "en")
        await ctx.reply(file=File(r"tts.mp3"))

    @command()
    async def gay(self, ctx: PretendContext, *, member: Member = Author):
        """
        Gay rate a member
        """
        a = 1
        if member.id == 461914901624127489:
            a = 100
        embed = Embed(
            color=self.bot.color,
            description=f"{member.mention} is **{random.randint(a, 100)}%** gay 🏳️‍🌈",
        )
        return await ctx.send(embed=embed)

    @command()
    async def furry(self, ctx: PretendContext, *, member: Member = Author):
        """
        Furry rate a member
        """
        a = 1
        embed = Embed(
            color=self.bot.color,
            description=f"{member.mention} is **{random.randint(a, 100)}%** a furry 🦊",
        )
        return await ctx.send(embed=embed)

    @command(name="dadjoke", aliases=["cringejoke"])
    async def dadjoke(self, ctx: PretendContext):
        """
        Get a random dad joke.
        """
        try:
            joke = await asyncio.wait_for(
                self.bot.session.get_json("https://icanhazdadjoke.com/slack"), timeout=2
            )
        except asyncio.TimeoutError:
            return await ctx.send_warning(
                "Womp Womp! Couldn't get a dad joke at this time."
            )
        return await ctx.pretend_send(f"{joke['attachments'][0]['text']}")

    @command(name="meme")
    async def meme(self, ctx: PretendContext):
        """
        Generate a random meme.
        """
        try:
            meme = await asyncio.wait_for(
                self.bot.session.get_json("https://meme-api.com/gimme"), timeout=4
            )
        except asyncio.TimeoutError:
            return await ctx.send_warning("Error fetching a meme.")
        embed = discord.Embed(color=0x2B2D31)
        embed.set_image(url=meme["url"])
        await ctx.send(embed=embed)

    @command(name="lick", aliases=["slurp"])
    async def lick(self, ctx: PretendContext, *, member: Member = Author):
        """
        Lick someone!
        """
        if ctx.author.id == member.id:
            return await ctx.send_error("You can't lick yourself!")
        res = ["You slurp that mf.", "Lick Lick!", "Slurp!"]
        embed = Embed(
            color=self.bot.color,
            description=f"You lick {member.nick or member.global_name or member.name}!",
        )
        try:
            lick = await asyncio.wait_for(
                self.bot.session.get_json(
                    "https://api.otakugifs.xyz/gif?reaction=lick&format=gif"
                ),
                timeout=6,
            )
        except asyncio.TimeoutError:
            return await ctx.send_error("There was an error with the API.")
        embed.set_footer(text=random.choice(res))
        embed.set_image(url=lick["url"])
        await ctx.reply(embed=embed)

    @command()
    async def pp(self, ctx: PretendContext, *, member: Member = Author):
        """
        Check someone's pp size
        """
        m = 15
        mn = 1
        if member.id in [1208472692337020999, 1174502631696252962, 1208472692337020999]:
            m = 100
            mn = 20
        embed = Embed(
            color=self.bot.color,
            description=f"{member.nick or member.global_name or member.name}'s penis\n\n8{'=' * random.randint(mn, m)}D",
        )
        await ctx.reply(embed=embed)

    @hybrid_command()
    async def kiss(self, ctx: PretendContext, *, member: Member):
        """
        Kiss a member
        """
        try:
            lol = await asyncio.wait_for(
                self.bot.session.get_json(
                    "https://api.otakugifs.xyz/gif?reaction=kiss&format=gif"
                ),
                timeout=2,
            )
        except asyncio.TimeoutError:
            return await ctx.send_error("There was an error with the API.")
        embed = Embed(
            color=self.bot.color,
            description=f"*Aww how cute!* **{ctx.author.name}** kissed **{member.name}**",
        )
        embed.set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def pinch(self, ctx: PretendContext, *, member: Member):
        """
        Pinch a member
        """

        response = await self.bot.session.get_json(
            "https://api.otakugifs.xyz/gif?reaction=pinch&format=gif"
        )
        embed = Embed(
            color=self.bot.color,
            description=f"**{ctx.author.name}** pinches **{member.name}**",
        )
        embed.set_image(url=response["url"])

        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def cuddle(self, ctx: PretendContext, *, member: Member):
        """
        Cuddle a member
        """
        try:
            lol = await asyncio.wait_for(
                self.bot.session.get_json(
                    "https://api.otakugifs.xyz/gif?reaction=cuddle&format=gif"
                ),
                timeout=2,
            )
        except asyncio.TimeoutError:
            return await ctx.send_error("There was an error with the API.")
        embed = Embed(
            color=self.bot.color,
            description=f"*Aww how cute!* **{ctx.author.name}** cuddles **{member.name}**",
        ).set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def hug(self, ctx: PretendContext, *, member: Member):
        """
        Hug a member
        """
        try:
            lol = await asyncio.wait_for(
                self.bot.session.get_json(
                    f"https://api.otakugifs.xyz/gif?reaction=hug&format=gif"
                ),
                timeout=2,
            )
        except asyncio.TimeoutError:
            return await ctx.send_error("There was an error with the API.")
        embed = Embed(
            color=self.bot.color,
            description=f"*Aww how cute!* **{ctx.author.name}** hugged **{member.name}**",
        ).set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def pat(self, ctx: PretendContext, *, member: Member):
        """
        Pat a member
        """
        try:
            lol = await asyncio.wait_for(
                self.bot.session.get_json(
                    f"https://api.otakugifs.xyz/gif?reaction=pat&format=gif"
                ),
                timeout=2,
            )
        except asyncio.TimeoutError:
            return await ctx.send_error("There was an error with the API.")
        embed = Embed(
            color=self.bot.color,
            description=f"*Aww how cute!* **{ctx.author.name}** pats **{member.name}**",
        ).set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def slap(self, ctx: PretendContext, *, member: Member):
        """
        Slap a member
        """
        try:
            lol = await asyncio.wait_for(
                self.bot.session.get_json(
                    f"https://api.otakugifs.xyz/gif?reaction=slap&format=gif"
                ),
                timeout=2,
            )
        except asyncio.TimeoutError:
            return await ctx.send_error("There was an error with the API.")
        embed = Embed(
            color=self.bot.color,
            description=f"**{ctx.author.name}** slaps **{member.name}***",
        ).set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def laugh(self, ctx: PretendContext):
        """
        Start laughing
        """
        try:
            lol = await asyncio.wait_for(
                self.bot.session.get_json(
                    f"https://api.otakugifs.xyz/gif?reaction=laugh&format=gif"
                ),
                timeout=2,
            )
        except asyncio.TimeoutError:
            return await ctx.send_error("There was an error with the API.")
        embed = Embed(
            color=self.bot.color, description=f"**{ctx.author.name}** laughs"
        ).set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def cry(self, ctx: PretendContext):
        """
        Start crying
        """
        try:
            lol = await asyncio.wait_for(
                self.bot.session.get_json(
                    f"https://api.otakugifs.xyz/gif?reaction=cry&format=gif"
                ),
                timeout=2,
            )
        except asyncio.TimeoutError:
            return await ctx.send_error("There was an error with the API.")

        embed = Embed(
            color=self.bot.color, description=f"**{ctx.author.name}** cries"
        ).set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def marry(self, ctx: PretendContext, *, member: AbleToMarry):
        """
        Marry a member
        """

        embed = Embed(
            color=self.marry_color,
            description=f"{self.wedding} {ctx.author.mention} wants to marry you. do you accept?",
        )
        view = MarryView(ctx, member)
        view.message = await ctx.reply(content=member.mention, embed=embed, view=view)

    @hybrid_command()
    async def marriage(self, ctx: PretendContext, *, member: User = Author):
        """
        View an user's marriage
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM marry WHERE $1 IN (author, soulmate)", member.id
        )
        if check is None:
            return await ctx.send_error(
                f"{'You are' if member == ctx.author else f'{member.mention} is'} not **married**"
            )

        embed = Embed(
            color=self.marry_color,
            description=f"{self.wedding} {f'{member.mention} is' if member != ctx.author else 'You are'} currently married to <@!{check[1] if check[1] != member.id else check[0]}> since **{self.bot.humanize_date(datetime.datetime.fromtimestamp(int(check['time'])))}**",
        )
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def divorce(self, ctx: PretendContext):
        """
        Divorce from your partner
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM marry WHERE $1 IN (author, soulmate)", ctx.author.id
        )
        if check is None:
            return await ctx.send_error("**You** are not **married**")

        async def button1_callback(interaction: Interaction) -> None:
            member = await self.bot.fetch_user(
                check["author"]
                if check["author"] != interaction.user.id
                else check["soulmate"]
            )
            await interaction.client.db.execute(
                "DELETE FROM marry WHERE $1 IN (author, soulmate)", interaction.user.id
            )
            embe = Embed(
                color=interaction.client.color,
                description=f"**{interaction.user.name}** divorced with their partner",
            )

            try:
                await member.send(
                    f"💔 It seems like your partner **{interaction.user}** decided to divorce :(. Your relationship with them lasted **{humanize.precisedelta(datetime.datetime.fromtimestamp(int(check['time'])), format=f'%0.0f')}**"
                )
            except:
                pass

            await interaction.response.edit_message(content=None, embed=embe, view=None)

        async def button2_callback(interaction: Interaction) -> None:
            embe = Embed(
                color=interaction.client.color,
                description=f"**{interaction.user.name}** you changed your mind",
            )
            await interaction.response.edit_message(content=None, embed=embe, view=None)

        await ctx.confirmation_send(
            f"{ctx.author.mention} are you sure you want to divorce?",
            button1_callback,
            button2_callback,
        )

    @hybrid_command(name="song", aliases=["music", "beat", "songinfo"])
    async def song(self, ctx: PretendContext, *, title: str):
        """
        get information about a song
        """

        headers = {
            "X-RapidAPI-Key": str(self.songkey),
            "X-RapidAPI-Host": "genius-song-lyrics1.p.rapidapi.com",
        }
        query = {"q": title, "per_page": 1, "page": 1}

        response = await self.bot.session.get_json(
            "https://genius-song-lyrics1.p.rapidapi.com/search/",
            headers=headers,
            params=query,
        )

        if not response:
            return await ctx.send_warning(f"No results found for **{title}**")

        info = response["hits"][0]["result"]

        try:
            thumbnail = info["song_art_image_url"]
        except KeyError:
            thumbnail = None

        if thumbnail:
            color = await self.bot.dominant_color(str(thumbnail))
        else:
            color = self.bot.color

        embed = (
            discord.Embed(
                title=info["title"],
                url=info["url"],
                color=color,
                timestamp=datetime.datetime.now(),
            )
            .set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
            .add_field(
                name="Artists",
                value=self.shorten(info["artist_names"], 33),
                inline=False,
            )
            .add_field(
                name="Release Date", value=info["release_date_for_display"], inline=True
            )
            .add_field(name="Hot", value=info["stats"]["hot"], inline=True)
            .add_field(name="Instrumental", value=info["instrumental"], inline=True)
            .set_footer(text=f"{int(info['stats']['pageviews']):,} views")
            .set_thumbnail(url=thumbnail or None)
        )

        if rows := info["featured_artists"]:
            artists = []

            for row in rows:
                artists.append(row["name"])

            embed.add_field(name="More Artists", value=", ".join(artists))

        await ctx.send(embed=embed)


async def setup(bot) -> None:
    await bot.add_cog(Fun(bot))
