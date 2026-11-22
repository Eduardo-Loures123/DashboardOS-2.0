"""Generate a DISABLED local task definition. Never register or activate it."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo


def prepare(output, database):
    root=Path(__file__).resolve().parents[1];database=Path(database).resolve()
    if not database.is_file() or not database.is_relative_to(root): raise ValueError('Use exclusivamente o SQLite local existente do projeto.')
    namespace='http://schemas.microsoft.com/windows/2004/02/mit/task';ET.register_namespace('',namespace)
    def node(parent,name,value=None):
        item=ET.SubElement(parent,'{'+namespace+'}'+name)
        if value is not None:item.text=str(value)
        return item
    task=ET.Element('{'+namespace+'}Task',version='1.2')
    node(node(task,'RegistrationInfo'),'Description','Limpeza LOCAL exclusiva de profile_activities após 30 dias. Não inicia Flask, SMTP ou fila. DESABILITADA.')
    trigger=node(node(task,'Triggers'),'TimeTrigger');repeat=node(trigger,'Repetition')
    node(repeat,'Interval','PT15M');node(repeat,'StopAtDurationEnd','false')
    node(trigger,'StartBoundary',datetime.now(ZoneInfo('America/Sao_Paulo')).replace(microsecond=0).isoformat());node(trigger,'Enabled','true')
    principal=node(node(task,'Principals'),'Principal');principal.set('id','Author')
    node(principal,'UserId',os.environ.get('USERDOMAIN','')+'\\'+os.environ.get('USERNAME',''))
    node(principal,'LogonType','InteractiveToken');node(principal,'RunLevel','LeastPrivilege')
    settings=node(task,'Settings')
    for name,value in [('MultipleInstancesPolicy','IgnoreNew'),('DisallowStartIfOnBatteries','false'),('StopIfGoingOnBatteries','false'),('StartWhenAvailable','true'),('RunOnlyIfNetworkAvailable','false'),('Enabled','false'),('Hidden','true'),('ExecutionTimeLimit','PT5M')]:node(settings,name,value)
    actions=node(task,'Actions');actions.set('Context','Author');execute=node(actions,'Exec')
    node(execute,'Command',root/'.venv/Scripts/pythonw.exe')
    node(execute,'Arguments','"'+str(root/'scripts/limpar_atividades.py')+'" --database "'+str(database)+'" --execute')
    node(execute,'WorkingDirectory',root)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    ET.ElementTree(task).write(output,encoding='utf-8',xml_declaration=True)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--database',required=True);args=parser.parse_args()
    print('Definição desabilitada preparada: '+str(prepare(args.output,args.database)))
