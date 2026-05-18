from .admin import create_admin_router
from .general import create_general_router
from .posts import create_posts_router
from .referrals import create_referrals_router


def setup_routers(state):
    state.dp.include_router(create_general_router(state))
    state.dp.include_router(create_admin_router(state))
    state.dp.include_router(create_referrals_router(state))
    state.dp.include_router(create_posts_router(state))
