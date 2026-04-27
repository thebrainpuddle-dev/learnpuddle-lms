from django.apps import AppConfig


class ChatbotConfig(AppConfig):
    name = "apps.chatbot"
    label = "chatbot"
    verbose_name = "AI Chatbot Tutor"

    def ready(self):
        pass  # Reserved for future signal registration
