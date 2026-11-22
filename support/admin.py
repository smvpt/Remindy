import logging
from html import escape

import requests
from django.contrib import admin, messages

from config import BOT_TOKEN

from .models import BotUser, Reminder, UserQuery

logger = logging.getLogger(__name__)

admin.site.site_header = "Remindy admin"
admin.site.site_title = "Remindy admin"
admin.site.index_title = "Bot administration"


def send_telegram_message(chat_id: int, text: str) -> bool:
    """Sends a message on behalf of the bot. Returns True on success."""
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )
    return response.ok


@admin.register(UserQuery)
class UserQueryAdmin(admin.ModelAdmin):
    list_display = ("display_username", "question", "is_answered", "created_at")
    list_filter = ("is_answered", "created_at")
    search_fields = ("username", "question", "user_id")
    readonly_fields = ("user_id", "username", "question", "is_answered", "created_at")
    fields = ("user_id", "username", "question", "created_at", "is_answered", "answer")
    date_hierarchy = "created_at"

    @admin.display(description="User", ordering="username")
    def display_username(self, obj):
        return obj.username or f"ID: {obj.user_id}"

    def has_add_permission(self, request):
        return False  # queries come only from the bot

    def save_model(self, request, obj, form, change):
        """Typing an answer and saving sends it to the user in Telegram."""
        if change and obj.answer and not obj.is_answered:
            try:
                if send_telegram_message(obj.user_id, f"⚠️ <b>Support reply:</b>\n\n{escape(obj.answer)}"):
                    obj.is_answered = True
                    self.message_user(request, "Reply sent to the user.", messages.SUCCESS)
                else:
                    self.message_user(request, "Telegram rejected the message.", messages.ERROR)
            except requests.RequestException as e:
                logger.exception("Failed to send support reply")
                self.message_user(request, f"Failed to send the reply: {e}", messages.ERROR)
        super().save_model(request, obj, form, change)


@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    list_display = ("user_id", "name", "timezone", "created_at")
    search_fields = ("user_id", "name")
    list_filter = ("timezone",)
    readonly_fields = ("user_id", "created_at")


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "text", "datetime", "is_sent")
    list_filter = ("is_sent",)
    search_fields = ("text", "user_id")
    readonly_fields = ("created_at",)
