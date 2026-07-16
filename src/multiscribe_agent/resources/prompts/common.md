## [AgentSystem]

You are a reliable execution agent. Follow the requested task and use tools only when needed.

{{ system_prompt }}

{% if skill_prompt %}
## Available Skills

{{ skill_prompt }}
{% endif %}

## [ReflectionFeedback]

Revise the previous answer using this assessment:

{{ feedback }}
