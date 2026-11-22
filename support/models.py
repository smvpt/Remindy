from django.db import models


class UserQuery(models.Model):
    """Every message a user sends to the bot. Admins can reply from the admin panel."""

    user_id = models.BigIntegerField("Telegram user ID")
    username = models.CharField("Username", max_length=150, blank=True, null=True)
    question = models.TextField("User message")
    answer = models.TextField("Support reply", blank=True, null=True)
    is_answered = models.BooleanField("Answered", default=False)
    created_at = models.DateTimeField("Received at", auto_now_add=True)

    class Meta:
        verbose_name = "User query"
        verbose_name_plural = "User queries"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Query from {self.username or self.user_id} ({self.created_at:%d.%m %H:%M})"


# The two models below map onto tables created by the bot itself (database.py),
# so Django must not create or migrate them: managed = False.

class BotUser(models.Model):
    user_id = models.BigIntegerField("Telegram user ID", primary_key=True)
    name = models.TextField("Name", blank=True, null=True)
    timezone = models.TextField("Timezone", default="UTC")
    created_at = models.DateTimeField("Joined at", blank=True, null=True)

    class Meta:
        managed = False
        db_table = "users"
        verbose_name = "Bot user"
        verbose_name_plural = "Bot users"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or str(self.user_id)


class Reminder(models.Model):
    user_id = models.BigIntegerField("Telegram user ID")
    text = models.TextField("Text")
    datetime = models.DateTimeField("Remind at (UTC)")
    is_sent = models.BooleanField("Sent", default=False)
    created_at = models.DateTimeField("Created at", blank=True, null=True)

    class Meta:
        managed = False
        db_table = "reminders"
        verbose_name = "Reminder"
        verbose_name_plural = "Reminders"
        ordering = ["datetime"]

    def __str__(self):
        return self.text
