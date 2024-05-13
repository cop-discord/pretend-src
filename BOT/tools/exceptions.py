from discord.ext.commands import CommandError


class LastFmException(CommandError):
    def __init__(self, message: str):
        """
        Exception raised when there is a lastfm specific error
        """

        self.message = message
        super().__init__(self.message)


class RenameRateLimit(CommandError):
    def __init__(
        self,
        message: str = "You renamed this channel too many times in a short amount of time",
    ):
        """
        Exception raised when a discord voice channel is about to hit an invalid for renaming
        """

        self.message = message
        super().__init__(self.message)


class WrongMessageLink(CommandError):
    def __init__(self, message: str = "This message does not belong to this server"):
        """
        Exception raised when the message link given doesn't belong to the guild the command has been ran in
        """

        self.message = message
        super().__init__(self.message)


class ApiError(CommandError):
    def __init__(self, status_code: int):
        """
        Exception raised when api requests return bad codes
        """

        self.status_code = status_code
        super().__init__(f"The API returned **{self.status_code}** as the status code")
