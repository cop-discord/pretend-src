import re
import discord
import datetime

from discord.ext import commands


class EmbedBuilder:
    def __init__(self):
        self.ok = "hi"

    def ordinal(self, num: int) -> str:
        """Convert from number to ordinal (10 - 10th)"""
        numb = str(num)
        if numb.startswith("0"):
            numb = numb.strip("0")
        if numb in ["11", "12", "13"]:
            return numb + "th"
        if numb.endswith("1"):
            return numb + "st"
        elif numb.endswith("2"):
            return numb + "nd"
        elif numb.endswith("3"):
            return numb + "rd"
        else:
            return numb + "th"

    def embed_replacement(self, user: discord.Member, params: str = None):
        """Replace embed variables"""
        if params is None:
            return None
        if user is None:
            return None
        if "{user}" in params:
            params = params.replace("{user}", str(user))
        if "{user.mention}" in params:
            params = params.replace("{user.mention}", user.mention)
        if "{user.name}" in params:
            params = params.replace("{user.name}", user.name)
        if "{user.id}" in params:
            params = params.replace("{user.id}", str(user.id))
        if "{user.avatar}" in params:
            params = params.replace("{user.avatar}", str(user.display_avatar.url))
        if "{user.joined_at}" in params:
            params = params.replace(
                "{user.joined_at}", discord.utils.format_dt(user.joined_at, style="R")
            )
        if "{user.created_at}" in params:
            params = params.replace(
                "{user.created_at}", discord.utils.format_dt(user.created_at, style="R")
            )
        if "{user.discriminator}" in params:
            params = params.replace("{user.discriminator}", user.discriminator)
        if "{guild.name}" in params:
            params = params.replace("{guild.name}", user.guild.name)
        if "{guild.count}" in params:
            params = params.replace("{guild.count}", str(user.guild.member_count))
        if "{guild.count.format}" in params:
            params = params.replace(
                "{guild.count.format}", self.ordinal(len(user.guild.members))
            )
        if "{guild.id}" in params:
            params = params.replace("{guild.id}", user.guild.id)
        if "{guild.created_at}" in params:
            params = params.replace(
                "{guild.created_at}",
                discord.utils.format_dt(user.guild.created_at, style="R"),
            )
        if "{guild.boost_count}" in params:
            params = params.replace(
                "{guild.boost_count}", str(user.guild.premium_subscription_count)
            )
        if "{guild.booster_count}" in params:
            params = params.replace(
                "{guild.booster_count}", str(len(user.guild.premium_subscribers))
            )
        if "{guild.boost_count.format}" in params:
            params = params.replace(
                "{guild.boost_count.format}",
                self.ordinal(user.guild.premium_subscription_count),
            )
        if "{guild.booster_count.format}" in params:
            params = params.replace(
                "{guild.booster_count.format}",
                self.ordinal(len(user.guild.premium_subscribers)),
            )
        if "{guild.boost_tier}" in params:
            params = params.replace("{guild.boost_tier}", str(user.guild.premium_tier))
        if "{guild.vanity}" in params:
            params = params.replace(
                "{guild.vanity}", "/" + user.guild.vanity_url_code or "none"
            )
        if "{invisible}" in params:
            params = params.replace("{invisible}", "2b2d31")
        if "{botcolor}" in params:
            params = params.replace("{botcolor}", "729bb0")
        if "{botavatar}" in params:
            params = params.replace(
                "{botavatar}",
                "https://images-ext-1.discordapp.net/external/gQinzaMi-EYOvq-VudfO8fWk21PD2NLefrk6QZyVyDs/%3Fsize%3D1024/https/cdn.discordapp.com/icons/1177424668328726548/a_229e85dbdae4f77c4accdf92ced9d822.gif",
            )
        if "{guild.icon}" in params:
            if user.guild.icon:
                params = params.replace("{guild.icon}", user.guild.icon.url)
            else:
                params = params.replace("{guild.icon}", "https://none.none")

        return params

    def get_parts(self, params: str) -> list:
        if params is None:
            return None
        params = params.replace("{embed}", "")
        return [p[1:][:-1] for p in params.split("$v")]

    def validator(self, text: str, max_len: int, error: str):
        if len(text) >= max_len:
            raise commands.BadArgument(error)

    def is_url(self, text: str, parameter: str):
        regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
        if not re.search(regex, text):
            raise commands.BadArgument(
                f"The **{parameter}** parameter got an invalid url"
            )

    def to_object(self, params: str) -> tuple:
        x = {}
        fields = []
        content = None
        view = discord.ui.View()
        delete_after = None

        for part in self.get_parts(params):

            if part.startswith("content:"):
                content = part[len("content:") :]
                self.validator(content, 2000, "Message content too long")

            if part.startswith("title:"):
                x["title"] = part[len("title:") :]
                self.validator(part[len("title:") :], 256, "Embed title too long")

            if part.startswith("url:"):
                x["url"] = part[len("url") :]
                self.is_url(part[len("url:") :], "URL")

            if part.startswith("description:"):
                x["description"] = part[len("description:") :]
                self.validator(
                    part[len("description:") :], 2048, "Embed description too long"
                )

            if part.startswith("color:"):
                try:
                    x["color"] = int(part[len("color:") :].replace("#", ""), 16)
                except:
                    x["color"] = int("808080", 16)

            if part.startswith("thumbnail:"):
                x["thumbnail"] = {"url": part[len("thumbnail:") :]}
                self.is_url(part[len("thumbnail:") :], "thumbnail")

            if part.startswith("image:"):
                x["image"] = {"url": part[len("image:") :]}
                self.is_url(part[len("image:") :], "image")

            if part == "timestamp":
                x["timestamp"] = datetime.datetime.now().isoformat()

            if part.startswith("delete:"):
                try:
                    delete_after = float(part[len("delete: ") :])
                except:
                    delete_after = None

            if part.startswith("author:"):
                author_parts = part[len("author: ") :].split(" && ")
                name = None
                url = None
                icon_url = None
                for z in author_parts:

                    if z.startswith("name:"):
                        name = z[len("name:") :]
                        self.validator(name, 256, "author name too long")

                    if z.startswith("icon:"):
                        icon_url = z[len("icon:") :]
                        self.is_url(icon_url, "author icon")

                    if z.startswith("url:"):
                        url = z[len("url:") :]
                        self.is_url(url, "author url")

                x["author"] = {"name": name}

                if icon_url:
                    x["author"]["icon_url"] = icon_url

                if url:
                    x["author"]["url"] = url

            if part.startswith("field:"):
                name = None
                value = None
                inline = False
                field_parts = part[len("field: ") :].split(" && ")
                for z in field_parts:

                    if z.startswith("name:"):
                        name = z[len("name:") :]
                        self.validator(name, 256, "field name too long")

                    if z.startswith("value:"):
                        value = z[len("value:") :]
                        self.validator(value, 1024, "field value too long")

                    if z.strip() == "inline":
                        inline = True

                fields.append({"name": name, "value": value, "inline": inline})

            if part.startswith("footer:"):
                text = None
                icon_url = None
                footer_parts = part[len("footer: ") :].split(" && ")
                for z in footer_parts:

                    if z.startswith("text:"):
                        text = z[len("text:") :]
                        self.validator(text, 2048, "footer text too long")

                    if z.startswith("icon:"):
                        icon_url = z[len("icon:") :]
                        self.is_url(icon_url, "footer icon")

                x["footer"] = {"text": text, "icon_url": icon_url}
            if part.startswith("button:"):
                z = part[len("button:") :].split(" && ")
                disabled = True
                style = discord.ButtonStyle.gray
                emoji = None
                label = None
                url = None
                for m in z:
                    if "label:" in m:
                        label = m.replace("label:", "")
                    if "url:" in m:
                        url = m.replace("url:", "").strip()
                        disabled = False
                    if "emoji:" in m:
                        emoji = m.replace("emoji:", "").strip()
                    if "disabled" in m:
                        disabled = True
                    if "style:" in m:
                        if m.replace("style:", "").strip() == "red":
                            style = discord.ButtonStyle.red
                        elif m.replace("style:", "").strip() == "green":
                            style = discord.ButtonStyle.green
                        elif m.replace("style:", "").strip() == "gray":
                            style = discord.ButtonStyle.gray
                        elif m.replace("style:", "").strip() == "blue":
                            style = discord.ButtonStyle.blurple

                view.add_item(
                    discord.ui.Button(
                        style=style,
                        label=label,
                        emoji=emoji,
                        url=url,
                        disabled=disabled,
                    )
                )

        if not x:
            embed = None
        else:

            if len(fields) > 25:
                raise commands.BadArgument(
                    "There are more than **25** fields in your embed"
                )

            x["fields"] = fields
            embed = discord.Embed.from_dict(x)
        return content, embed, view, delete_after

    def copy_embed(self, message: discord.Message) -> str:
        to_return = ""
        if embeds := message.embeds:
            embed: dict = discord.Embed.to_dict(embeds[0])
            to_return += "{embed}"

            if embed.get("color"):
                to_return += "{color: " + hex(embed["color"]).replace("0x", "#") + "}"

            if embed.get("title"):
                to_return += "$v{title: " + embed["title"] + "}"

            if embed.get("description"):
                to_return += "$v{description: " + embed["description"] + "}"

            if embed.get("author"):
                author = embed["author"]
                to_return += "$v{author: "

                if author.get("name"):
                    to_return += f"name: {author.get('name')}"

                if author.get("icon_url"):
                    to_return += f" && icon: {author.get('icon_url')}"

                if author.get("url"):
                    to_return += f" && url: {author.get('url')}"

                to_return += "}"

            if embed.get("thumbnail"):
                to_return += "$v{thumbnail: " + embed["thumbnail"]["url"]

            if embed.get("image"):
                to_return += "$v{image: " + embed["image"]["url"] + "}"

            if embed.get("fields"):
                for field in embed["fields"]:
                    to_return += (
                        "$v{field: "
                        + f"name: {field['name']} && value: {field['value']}{' && inline' if field['inline'] else ''}"
                        + "}"
                    )

            if embed.get("footer"):
                to_return += "$v{footer: "
                footer = embed["footer"]

                if footer.get("text"):
                    to_return += f"text: {footer.get('text')}"

                if footer.get("icon_url"):
                    to_return += f" && icon: {footer.get('icon_url')}"

                to_return += "}"

        if message.content:
            to_return += "$v{content: " + message.content + "}"

        return to_return


class EmbedScript(commands.Converter):

    async def convert(self, ctx: commands.Context, argument: str):
        x = EmbedBuilder().to_object(
            EmbedBuilder().embed_replacement(ctx.author, argument)
        )
        if x[0] or x[1]:
            if x[3]:
                return {
                    "content": x[0],
                    "embed": x[1],
                    "view": x[2],
                    "delete_after": x[3],
                }
            else:
                return {"content": x[0], "embed": x[1], "view": x[2]}

        return {"content": EmbedBuilder().embed_replacement(ctx.author, argument)}

    async def alt_convert(self, member: discord.Member, argument: str):
        x = EmbedBuilder().to_object(EmbedBuilder().embed_replacement(member, argument))
        if x[0] or x[1]:
            if x[3]:
                return {
                    "content": x[0],
                    "embed": x[1],
                    "view": x[2],
                    "delete_after": x[3],
                }
            else:
                return {"content": x[0], "embed": x[1], "view": x[2]}

        return {"content": EmbedBuilder().embed_replacement(member, argument)}
