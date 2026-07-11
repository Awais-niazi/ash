from django.urls import path
from .views import (
    ChatView, ResetView, MorningBriefingView, SpeakView,
    VapidKeyView, PushSubscribeView, PushUnsubscribeView, PushTestView,
)

urlpatterns = [
    path("chat/", ChatView.as_view(), name="chat"),
    path("reset/", ResetView.as_view(), name="reset"),
    path("briefing/", MorningBriefingView.as_view(), name="briefing"),
    path("speak/", SpeakView.as_view(), name="speak"),
    path("push/key/", VapidKeyView.as_view(), name="push-key"),
    path("push/subscribe/", PushSubscribeView.as_view(), name="push-subscribe"),
    path("push/unsubscribe/", PushUnsubscribeView.as_view(), name="push-unsubscribe"),
    path("push/test/", PushTestView.as_view(), name="push-test"),
]
