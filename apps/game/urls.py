from django.urls import path

from .views import game_session_player_voters

urlpatterns = [
    path(
        'game-session/<str:session_id>/players/<int:player_id>/voters/',
        game_session_player_voters,
        name='game-session-player-voters',
    ),
]
