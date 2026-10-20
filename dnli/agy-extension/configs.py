"""agy 1.3.3 model list from brief-e-agy.md; no discovery/model calls."""
MODELS = tuple(f'{model}-{effort}' for model in
               ('gemini-3.8-flash', 'claude-opus-5-5', 'claude-sonnet-5-5')
               for effort in ('low', 'medium', 'high')) + ('gpt-oss-120b-medium',)
CONFIGS = tuple('agy:' + m for m in MODELS)

# Fail closed until approved probes establish additional side-effect-free types.
SAFE_STEP_TYPES = ('user_input', 'agent_response')
SAFE_STEP_FIELDS = ('conversation_id', 'step_index', 'state', 'step_type',
                    'text_delta', 'duration_seconds', 'usage')
SAFE_USAGE_FIELDS = ('input_tokens', 'output_tokens', 'thinking_tokens',
                     'cache_read_tokens', 'total_tokens')
# Explicit nested schema; no inferred safe types/fields before approved probes.
STEP_TYPE_FIELDS = ('step_type', 'type', 'kind', 'message_type', 'content_type')
SAFE_NESTED_FIELDS = SAFE_STEP_FIELDS + STEP_TYPE_FIELDS
TOOL_FIELDS = ('name', 'command', 'url', 'query', 'function', 'action')
KNOWN_TOOL_NAMES = ('search_web', 'read_url', 'tool', 'tool_call', 'tool_use',
                    'run_command', 'execute_command', 'read_file', 'write_file',
                    'edit_file', 'shell', 'bash', 'powershell')
RATE_PATTERNS = (r'(?<!\w)429(?!\w)', r'\bRESOURCE_EXHAUSTED\b',
                 r'\brate[ _-]+limit(?:ed|ing|[ _-]+exceeded)?\b',
                 r'\bquota[ _-]+(?:exceeded|exhausted)\b', r'\btoo many requests\b')

def validate_rate_patterns(patterns):
    import re
    if not isinstance(patterns, (list, tuple)) or not patterns or any(
            not isinstance(p, str) or not p.strip() for p in patterns):
        raise ValueError('rate patterns must be a nonempty string list')
    for pattern in patterns:
        re.compile(pattern)
    return tuple(patterns)

def file_config(cfg):
    if cfg not in CONFIGS:
        raise ValueError(cfg)
    return cfg.replace(':', '_')
