import inspect

import webapp2_extras.local

# request_cache is similar to layer_cache, except it only memoizes results
# for each individual request. If you need to cache results for longer than
# a single request, use layer_cache.
#
# _____Explanation by examples:_____
#
# import request_cache
#
# @request_cache.cache()
# def calculate_user_averages():
# ... do lots of long-running work...
#
# Cache using key generated by utility function that
# varies the key based on the function's input parameters:
#
# @request_cache.cache_with_key_fxn(
#     lambda object: "request_cache_key_for_object_%s" % object.id())
# def calculate_object_average(object):
#   ... do lots of long-running work...
#   return result_for_cache

_LOCAL = webapp2_extras.local.Local()
_DUMMY_VALUE = object()


def accepts_kwargs(target):
    args, varargs, varkw, defaults = inspect.getargspec(target)
    return varkw is not None


def cache():
    def decorator(target):
        key = "__request_cache_%s.%s__" % (target.__module__, target.__name__)

        def wrapper(*args, **kwargs):
            return request_cache_check_set_return(
                target,
                lambda *args, **kwargs: key,
                *args, **kwargs)

        return wrapper
    return decorator


def cache_with_key_fxn(key_fxn):
    def decorator(target):
        def wrapper(*args, **kwargs):
            return request_cache_check_set_return(target, key_fxn,
                                                  *args, **kwargs)
        return wrapper
    return decorator


def request_cache_check_set_return(
        target,
        key_fxn,
        *args,
        **kwargs):

    key = key_fxn(*args, **kwargs)

    bust_cache = False
    if "bust_cache" in kwargs:
        bust_cache = kwargs["bust_cache"]
        if not accepts_kwargs(target):
            # delete from kwargs so it's not passed to the target
            del kwargs["bust_cache"]

    if not bust_cache:
        # Access thread-local data once with getattr rather than twice in the
        # naive pattern -- if has(key): return get(key)
        result = getattr(_LOCAL, key, _DUMMY_VALUE)
        if result is not _DUMMY_VALUE:
            return result

    result = target(*args, **kwargs)

    # In case the key's value has been changed by target's execution
    key = key_fxn(*args, **kwargs)

    set(key, result)

    return result


def has(key):
    return hasattr(_LOCAL, key)


def get(key):
    return getattr(_LOCAL, key, None)


def set(key, value, **kwargs):
    setattr(_LOCAL, key, value)


def flush():
    _LOCAL.__release_local__()


class RequestCacheMiddleware(object):
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Clear the cache before and after every request.
        try:
            # TODO(chris): remove flush() at beginning of the request. we
            # should only have to clear at the end of a request, but without
            # this some end-to-end tests break because things exist in the
            # cache before the request starts. Perhaps gae_bingo populating
            # the user object?
            flush()
            return self.app(environ, start_response)
        finally:
            flush()