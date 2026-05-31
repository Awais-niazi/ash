from django.urls import path
from .views import ChatView, ResetView, MorningBriefingView

urlpatterns = [
    path("chat/", ChatView.as_view(), name="chat"),
    path("reset/", ResetView.as_view(), name="reset"),
    path("briefing/", MorningBriefingView.as_view(), name="briefing"),
]