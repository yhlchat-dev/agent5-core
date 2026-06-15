# -*- coding: utf-8 -*-
import os
from threading import RLock
from functools import wraps

_config_lock = RLock()

_initial_mode = os.environ.get('AGENT_RUN_MODE', 'default')
if os.environ.get('AGENT_TEST_MODE') == 'cognitive_only':
    _initial_mode = 'cognitive_only'

RUN_MODE = _initial_mode


def is_cognitive_only():
    with _config_lock:
        return RUN_MODE == 'cognitive_only'


def reload_run_mode():
    global RUN_MODE
    with _config_lock:
        RUN_MODE = os.environ.get('AGENT_RUN_MODE', 'default')
        if os.environ.get('AGENT_TEST_MODE') == 'cognitive_only':
            RUN_MODE = 'cognitive_only'
        print(f'[SYSTEM] RUN_MODE reloaded: {RUN_MODE}')
        return RUN_MODE


def cognitive_guard(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if is_cognitive_only():
            print(f'[COGNITIVE_ONLY][GUARD] blocked: {func.__name__}')
            return {"skipped": True, "reason": "cognitive_only mode"}
        return func(*args, **kwargs)
    return wrapper


def cognitive_guard_async(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if is_cognitive_only():
            print(f'[COGNITIVE_ONLY][GUARD] blocked: {func.__name__}')
            return {"skipped": True, "reason": "cognitive_only mode"}
        return await func(*args, **kwargs)
    return wrapper
