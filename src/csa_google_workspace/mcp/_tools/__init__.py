"""One module per tool axis. `create_server` composes them; none of them knows the others.

The split is what lets the planned flavour switch be a *registration-time* filter — a tool
the flavour excludes simply is not registered, rather than existing and refusing. A tool
that exists and refuses still spends the model's attention and still has to explain itself
in its own description.
"""
from .auth import register_auth_tools
from .comments import register_comment_tools
from .config import register_config_tools
from .content import register_content_tools
from .files import register_file_tools

__all__ = ["register_auth_tools", "register_comment_tools", "register_config_tools",
           "register_content_tools", "register_file_tools"]
