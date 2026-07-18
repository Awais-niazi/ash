from django.urls import path
from .views import (
    ChatView, ResetView, MorningBriefingView, SpeakView, NotifyTestView,
)

urlpatterns = [
    path("chat/", ChatView.as_view(), name="chat"),
    path("reset/", ResetView.as_view(), name="reset"),
    path("briefing/", MorningBriefingView.as_view(), name="briefing"),
    path("speak/", SpeakView.as_view(), name="speak"),
    path("notify/test/", NotifyTestView.as_view(), name="notify-test"),
]
