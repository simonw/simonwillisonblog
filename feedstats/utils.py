from functools import wraps
from .models import SubscriberCount
import datetime
import re

subscribers_re = re.compile(r"(\d+) subscribers")


def count_subscribers(view_fn):
    @wraps(view_fn)
    def inner_fn(request, *args, **kwargs):
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        match = subscribers_re.search(user_agent)
        if match:
            count = int(match.group(1))
            today = datetime.date.today()
            simplified_user_agent = subscribers_re.sub("X subscribers", user_agent)
            # Do we have this one yet?
            if not SubscriberCount.objects.filter(
                path=request.path,
                count=count,
                user_agent=simplified_user_agent,
                created__year=today.year,
                created__month=today.month,
                created__day=today.day,
            ).exists():
                SubscriberCount.objects.create(
                    path=request.path,
                    count=count,
                    user_agent=simplified_user_agent,
                )
        return view_fn(request, *args, **kwargs)

    return inner_fn
