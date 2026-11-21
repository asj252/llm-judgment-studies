from pathlib import Path
import json
root=Path(__file__).resolve().parent
for number, table in sorted(json.loads((root/'manuscript_tables.json').read_text(encoding='utf-8')).items(),key=lambda item:int(item[0])):
    print('Table '+number+': '+table['title'])
    print(' | '.join(table['header']))
    for row in table['rows']: print(' | '.join(row))
print(json.dumps(json.loads((root/'figure_data.json').read_text(encoding='utf-8')),ensure_ascii=False,indent=2))
