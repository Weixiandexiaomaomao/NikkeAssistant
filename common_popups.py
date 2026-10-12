"""Common popup interrupts return to the interrupted task's recognition step."""
import copy

REWARD_INTERRUPT = '[JumpBack]CommonRewardDismiss'
ANNOUNCEMENT_INTERRUPT = '[JumpBack]CommonAnnouncementDismiss'
SOCIAL_NOTICE_INTERRUPT = '[JumpBack]CommonSocialNoticeDismiss'


def with_common_popups(pipeline):
    result = copy.deepcopy(pipeline)
    for name, node in result.items():
        if name in ('CommonRewardDismiss','CommonAnnouncementDismiss','CommonSocialNoticeDismiss'):
            continue
        next_nodes = node.get('next', [])
        if isinstance(next_nodes, str):
            next_nodes = [next_nodes]
        if next_nodes:
            interrupts = (ANNOUNCEMENT_INTERRUPT, SOCIAL_NOTICE_INTERRUPT, REWARD_INTERRUPT)
            node['next'] = [*interrupts, *[item for item in next_nodes if item not in interrupts]]
    return result
