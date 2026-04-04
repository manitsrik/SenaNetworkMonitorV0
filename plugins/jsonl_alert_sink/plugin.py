import json
import os
from datetime import datetime


class Plugin:
    """Simple integration plugin that appends alert events to a local JSONL file."""

    def send(self, payload, config, context=None):
        context = context or {}
        file_path = (config or {}).get('file_path') or 'plugin_logs/integration_alerts.jsonl'
        write_pretty = bool((config or {}).get('write_pretty', False))

        abs_path = file_path
        if not os.path.isabs(abs_path):
            abs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), file_path)

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        record = {
            'written_at': datetime.now().isoformat(),
            'is_test': bool(context.get('is_test')),
            'payload': payload,
        }

        with open(abs_path, 'a', encoding='utf-8') as handle:
            if write_pretty:
                handle.write(json.dumps(record, ensure_ascii=False, indent=2))
                handle.write('\n')
            else:
                handle.write(json.dumps(record, ensure_ascii=False))
                handle.write('\n')

        return {
            'success': True,
            'message': f'Alert written to {abs_path}',
            'output_path': abs_path,
        }
