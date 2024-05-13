import arrow
import asyncio
import datetime
import discord

from ..bot import Pretend
from ..helpers import PretendContext

from discord import User, Member
from discord.ext.commands import Converter, BadArgument, MemberConverter

from pydantic import BaseModel
from typing import Optional, Tuple
from timezonefinder import TimezoneFinder


class BirthdaySchema(BaseModel):
    name: str
    date: str
    birthday: str


class TimezoneSchema(BaseModel):
    timezone: str
    date: str


class Timezone:
    def __init__(self, bot: Pretend):
        self.bot = bot

        self.week_days = {
            0: "Monday",
            1: "Tuesday",
            2: "Wednesday",
            3: "Thursday",
            4: "Friday",
            5: "Saturday",
            6: "Sunday",
        }

        self.months = {
            1: "January",
            2: "February",
            3: "March",
            4: "April",
            5: "May",
            6: "June",
            7: "July",
            8: "August",
            9: "September",
            10: "October",
            11: "November",
            12: "December",
        }

    async def get_lat_long(self, location: str) -> Optional[dict]:
        params = {"q": location, "format": "json"}

        results = await self.bot.session.get_json(
            "https://nominatim.openstreetmap.org/search", params=params
        )
        if len(results) == 0:
            return None

        return {"lat": float(results[0]["lat"]), "lng": float(results[0]["lon"])}

    async def get_timezone(self, member: Member) -> Optional[str]:
        timezone = await self.bot.db.fetchval(
            "SELECT zone FROM timezone WHERE user_id = $1", member.id
        )

        if not timezone:
            return None

        local = arrow.utcnow().to(timezone).naive
        hour = local.strftime("%I:%M %p")
        week_day = self.week_days.get(local.weekday())
        month = self.months.get(local.month)
        day = self.bot.ordinal(local.day)
        return f"{week_day} {month} {day} {hour}"

    async def set_timezone(self, member: Member, location: str) -> str:
        obj = TimezoneFinder()
        kwargs = await self.get_lat_long(location)

        if not kwargs:
            raise BadArgument("Wrong location given")

        timezone = await asyncio.to_thread(obj.timezone_at, **kwargs)
        local = arrow.utcnow().to(timezone).naive
        check = await self.bot.db.fetchrow(
            "SELECT * FROM timezone WHERE user_id = $1", member.id
        )

        if not check:
            await self.bot.db.execute(
                "INSERT INTO timezone VALUES ($1,$2)", member.id, timezone
            )
        else:
            await self.bot.db.execute(
                "UPDATE timezone SET zone = $1 WHERE user_id = $2", timezone, member.id
            )

        hour = local.strftime("%I:%M %p")
        week_day = self.week_days.get(local.weekday())
        month = self.months.get(local.month)
        day = self.bot.ordinal(local.day)

        payload = {"timezone": timezone, "date": f"{week_day} {month} {day} {hour}"}

        return TimezoneSchema(**payload)


class TimezoneMember(MemberConverter):
    async def convert(self, ctx: PretendContext, argument: str):

        if not argument:
            return None

        try:
            member = await super().convert(ctx, argument)
        except:
            raise BadArgument("Member not found")

        tz = Timezone(ctx.bot)
        result = await tz.get_timezone(member)

        if not result:
            raise BadArgument("Timezone **not** found for this member")

        return [member, result]


class TimezoneLocation(Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        tz = Timezone(ctx.bot)
        return await tz.set_timezone(ctx.author, argument)


class BdayDate(Converter):
    async def convert(self, ctx: PretendContext, argument: str):
        bdays = argument.split()

        if len(bdays) < 2:
            raise BadArgument(
                "This is not a correct birthday format!\nPlease make sure you are following the example: `January 19`"
            )

        return await Birthday(ctx.bot).set_bday(ctx.author, bdays[0], bdays[1])


class BdayMember(MemberConverter):
    async def convert(self, ctx: PretendContext, argument: str):
        if argument is None:
            return None

        try:
            member = await super().convert(ctx, argument)
        except:
            raise BadArgument("Member **not** found")

        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM bday WHERE user_id = $1", member.id
        )
        if not check:
            raise BadArgument(
                f"{f'**You** don' if member == ctx.author else f'**{member.name}** doesn'}'t have a **birthday** configured"
            )

        payload = {
            "name": member.name,
            "date": f"""on {Timezone(ctx.bot).months.get(check['month'])} {ctx.bot.ordinal(check['day'])}""",
            "birthday": await Birthday(ctx.bot).get_bday(member),
        }

        return BirthdaySchema(**payload)


class Birthday:
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.months = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }

    async def set_bday(self, member: Member, month: str, day: str) -> Tuple[str, str]:
        check = await self.bot.db.fetchrow(
            "SELECT * FROM bday WHERE user_id = $1", member.id
        )
        mon = self.months.get(month.lower())

        try:
            d = int(day)
        except ValueError:
            raise BadArgument(f"**{day}** is not a valid day number")

        if not mon:
            raise BadArgument(f"**{month}** is not a valid month")

        try:
            now = datetime.datetime.now()
            bday = datetime.datetime(now.year, self.months.get(month.lower()), int(day))
            print(str(bday.timestamp()))
        except ValueError:
            raise BadArgument("This is **not** a valid birthday date")

        args = [member.id, mon, d]

        if not check:
            await self.bot.db.execute("INSERT INTO bday VALUES ($1,$2,$3)", *args)
        else:
            await self.bot.db.execute(
                "UPDATE bday SET month = $2, day = $3 WHERE user_id = $1", *args
            )

        return (f"on {month} {self.bot.ordinal(day)}", await self.get_bday(member))

    async def get_bday(self, member: User) -> Optional[str]:
        """get a user's birthday"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM bday WHERE user_id = $1", member.id
        )

        if not check:
            return None

        now = datetime.datetime.now()
        bday = datetime.datetime(now.year, check["month"], check["day"])

        if bday.day == now.day and bday.month == now.month:
            return "today"

        if bday.timestamp() < now.timestamp():
            bday = datetime.datetime(now.year + 1, check["month"], check["day"])

        if (bday - now).total_seconds() < 3600 * 48:
            return "tomorrow"

        return self.bot.humanize_date(bday)


def get_color(value: str):
    if value.lower() in ("random"):
        return discord.Color.random()
    elif value.lower() in ("invisible", "invis"):
        return discord.Color.from_str("#2b2d31")
    elif value.lower() == "black":
        return discord.Color.from_str("#000001")

    value = COLORS.get(str(value).lower()) or value
    try:
        color = discord.Color(int(value.replace("#", ""), 16))
    except ValueError:
        return None

    if not color.value > 16777215:
        return color
    else:
        return None


COLORS = {
    "aliceblue": "#f0f8ff",
    "antiquewhite": "#faebd7",
    "aqua": "#00ffff",
    "aquamarine": "#7fffd4",
    "azure": "#f0ffff",
    "beige": "#f5f5dc",
    "bisque": "#ffe4c4",
    "black": "#000000",
    "blanchedalmond": "#ffebcd",
    "blue": "#0000ff",
    "blueviolet": "#8a2be2",
    "brown": "#a52a2a",
    "burlywood": "#deb887",
    "cadetblue": "#5f9ea0",
    "chartreuse": "#7fff00",
    "chocolate": "#d2691e",
    "coral": "#ff7f50",
    "cornflowerblue": "#6495ed",
    "cornsilk": "#fff8dc",
    "crimson": "#dc143c",
    "cyan": "#00ffff",
    "darkblue": "#00008b",
    "darkcyan": "#008b8b",
    "darkgoldenrod": "#b8860b",
    "darkgray": "#a9a9a9",
    "darkgrey": "#a9a9a9",
    "darkgreen": "#006400",
    "darkkhaki": "#bdb76b",
    "darkmagenta": "#8b008b",
    "darkolivegreen": "#556b2f",
    "darkorange": "#ff8c00",
    "darkorchid": "#9932cc",
    "darkred": "#8b0000",
    "darkviolet": "#9400d3",
    "deeppink": "#ff1493",
    "deepskyblue": "#00bfff",
    "dimgray": "#696969",
    "dimgrey": "#696969",
    "dodgerblue": "#1e90ff",
    "firebrick": "#b22222",
    "floralwhite": "#fffaf0",
    "forestgreen": "#228b22",
    "fuchsia": "#ff00ff",
    "gainsboro": "#dcdcdc",
    "ghostwhite": "#f8f8ff",
    "gold": "#ffd700",
    "goldenrod": "#daa520",
    "gray": "#808080",
    "grey": "#808080",
    "green": "#008000",
    "greenyellow": "#adff2f",
    "honeydew": "#f0fff0",
    "hotpink": "#ff69b4",
    "indianred": "#cd5c5c",
    "indigo": "#4b0082",
    "ivory": "#fffff0",
    "khaki": "#f0e68c",
    "lavender": "#e6e6fa",
    "lavenderblush": "#fff0f5",
    "lawngreen": "#7cfc00",
    "lemonchiffon": "#fffacd",
    "lightblue": "#add8e6",
    "lightcoral": "#f08080",
    "lightcyan": "#e0ffff",
    "lightgoldenrodyellow": "#fafad2",
    "lightgray": "#d3d3d3",
    "lightyellow": "#ffffe0",
    "lime": "#00ff00",
    "limegreen": "#32cd32",
    "linen": "#faf0e6",
    "magenta": "#ff00ff",
    "maroon": "#800000",
    "navy": "#000080",
    "oldlace": "#fdf5e6",
    "olive": "#808000",
    "olivedrab": "#6b8e23",
    "orange": "#ffa500",
    "peru": "#cd853f",
    "pink": "#ffc0cb",
    "plum": "#dda0dd",
    "powderblue": "#b0e0e6",
    "purple": "#800080",
    "red": "#ff0000",
    "rosybrown": "#bc8f8f",
    "royalblue": "#4169e1",
    "saddlebrown": "#8b4513",
    "salmon": "#fa8072",
    "snow": "#fffafa",
    "springgreen": "#00ff7f",
    "steelblue": "#4682b4",
    "tan": "#d2b48c",
    "teal": "#008080",
    "thistle": "#d8bfd8",
    "tomato": "#ff6347",
    "turquoise": "#40e0d0",
    "violet": "#ee82ee",
    "wheat": "#f5deb3",
    "white": "#ffffff",
    "whitesmoke": "#f5f5f5",
    "yellow": "#ffff00",
}
