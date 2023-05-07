from collections import defaultdict

# since so many places were importing these four decorators
# it was causing a *lot* of circular imports.
# so I decided to put them here to solve most of them


command_handlers = dict()
event_listeners = defaultdict(set)
publish_args = dict()
consume_args = dict()


def handler(command):
    def wrapper(f):
        if f in command_handlers:
            raise ValueError(f"Command {command} already has a handler")
        command_handlers[command] = f
        return f

    return wrapper


def listener(event):
    def wrapper(f):
        event_listeners[event].add(f)
        return f

    return wrapper


def publish(ttl=None, dead_event=None):
    def inner(message):
        publish_args[message] = dict(ttl=ttl, dead_event=dead_event)
        return message

    return inner


def consume(
    error_factory=None,
    requeue=False,
    raise_on_ok=False,
):
    def inner(message):
        consume_args[message] = dict(
            error_factory=error_factory,
            requeue=requeue,
            raise_on_ok=raise_on_ok,
        )
        return message

    return inner