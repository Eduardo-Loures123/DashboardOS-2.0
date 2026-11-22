"""Bounded, explicit-schema XLSX analysis. Uploads never become trusted records."""
from copy import deepcopy
from datetime import date, datetime
from io import BytesIO
from pathlib import PurePosixPath
import math
import re
import zipfile
from xml.etree import ElementTree

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel

from .schema import SCHEMA

MAX_UPLOAD = 5 * 1024 * 1024
MAX_EXPANDED = 32 * 1024 * 1024
MAX_ROWS = 5000
MAX_CELLS = 150000
DATE_FIELDS = {'admissao', 'abertura', 'previsao', 'conclusao', 'concessao', 'vencimento', 'solicitacao'}
DERIVED = {'Funcionarios': set(), 'Equipes': {'quantidade_funcionarios','quantidade_os','quantidade_acessos'},
           'OrdensServico': {'equipe','nome_funcionario','dias','situacao'},
           'Acessos': {'equipe','nome_funcionario','dias','situacao'}, 'Renovacoes': {'equipe','nome_funcionario'}}
REFERENCES = [('Funcionarios','equipe','Equipes'), ('Equipes','responsavel','Funcionarios'),
              ('OrdensServico','funcionario','Funcionarios'), ('Acessos','funcionario','Funcionarios'),
              ('Renovacoes','acesso','Acessos'), ('Renovacoes','responsavel','Funcionarios')]


def safe_filename(value):
    return re.sub(r'[\x00-\x1f\x7f]','',str(value or 'arquivo.xlsx').replace('\\','/').split('/')[-1])[:120] or 'arquivo.xlsx'


def _check_archive(content):
    if not content or len(content) > MAX_UPLOAD:
        raise ValueError('Selecione um arquivo XLSX de até 5 MB.')
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries=archive.infolist()
            if not entries or len(entries)>150 or len({e.filename for e in entries})!=len(entries):
                raise ValueError('Estrutura XLSX inválida ou excessiva.')
            if sum(e.file_size for e in entries)>MAX_EXPANDED:
                raise ValueError('O conteúdo expandido excede 32 MB.')
            for entry in entries:
                path=PurePosixPath(entry.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in entry.filename or ':' in entry.filename or entry.flag_bits & 1:
                    raise ValueError('Estrutura XLSX não permitida.')
                if entry.is_dir():continue
                if entry.file_size>MAX_EXPANDED or entry.file_size/max(1,entry.compress_size)>1000:
                    raise ValueError('Compactação excessiva no arquivo XLSX.')
                lower=entry.filename.lower()
                if not (lower.endswith('.xml') or lower.endswith('.rels')) or any(
                    part in lower for part in ('vba','external','embedding','activex','connections','querytable','customxml')):
                    raise ValueError('O arquivo contém macros, anexos ou referências não suportadas.')
                payload=archive.read(entry)
                if b'\x00' in payload or b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
                    raise ValueError('Declarações XML não permitidas.')
                tree=ElementTree.fromstring(payload)
                if lower.endswith('.rels') and any(node.get('TargetMode','').lower()=='external' for node in tree):
                    raise ValueError('Referências externas não são permitidas.')
            if not {'[Content_Types].xml','xl/workbook.xml'}.issubset(archive.namelist()):
                raise ValueError('O arquivo não possui uma estrutura XLSX válida.')
    except (zipfile.BadZipFile, ElementTree.ParseError, RuntimeError, OSError, KeyError, NotImplementedError):
        raise ValueError('Arquivo XLSX corrompido ou inválido.') from None


def _date_value(value, epoch):
    if value is None or value=='':return ''
    if isinstance(value, bool):raise ValueError('Data inválida.')
    if isinstance(value,(int,float)):
        if not math.isfinite(value):raise ValueError('Data numérica inválida.')
        try:value=from_excel(value,epoch)
        except (ValueError,OverflowError):raise ValueError('Data numérica inválida.') from None
    if isinstance(value,datetime):return value.date().isoformat()
    if isinstance(value,date):return value.isoformat()
    value=str(value).strip()
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):return date.fromisoformat(value).isoformat()
        if re.match(r'^\d{4}-\d{2}-\d{2}[T ]',value):return datetime.fromisoformat(value).date().isoformat()
        if re.fullmatch(r'\d{2}/\d{2}/\d{4}',value):
            day,month,year=map(int,value.split('/'))
            if day<=12:raise ValueError('Data ambígua: use AAAA-MM-DD ou uma célula de data do Excel.')
            return date(year,month,day).isoformat()
    except (ValueError,OverflowError) as error:
        if 'ambígua' in str(error):raise
        raise ValueError('Data inválida: use AAAA-MM-DD ou uma célula de data do Excel.') from None
    raise ValueError('Data inválida: use AAAA-MM-DD ou uma célula de data do Excel.')


def read_upload(content, filename):
    if not str(filename).lower().endswith('.xlsx'):raise ValueError('Formato não suportado. Selecione um arquivo .xlsx.')
    _check_archive(content)
    tables={};errors=[];total_rows=0;total_cells=0
    try:
        book=load_workbook(BytesIO(content),read_only=True,data_only=False,keep_links=False)
    except Exception:
        raise ValueError('Não foi possível ler o arquivo XLSX. Confira sua estrutura.') from None
    try:
        unknown=[name for name in book.sheetnames if name not in SCHEMA]
        if unknown:raise ValueError('Abas não suportadas: '+', '.join(unknown)+'. Use o Excel exportado por Visão Geral ou por uma tela de cadastros; relatórios agregados não são importáveis.')
        for sheet in book:
            name=sheet.title
            if sheet.max_row and sheet.max_row>MAX_ROWS+1:raise ValueError('Limite de 5.000 registros por arquivo excedido.')
            if sheet.max_column and sheet.max_column>32:raise ValueError('Número excessivo de colunas.')
            if sheet.sheet_state!='visible':
                raise ValueError('Use abas visíveis no arquivo de importação.')
            # Ignore untrusted dimension metadata; count the rows and cells actually streamed.
            sheet.reset_dimensions()
            records=sheet.iter_rows();header_cells=next(records,())
            headers=[cell.value for cell in header_cells]
            while headers and headers[-1] is None:headers.pop()
            if len(headers)>32:raise ValueError('Número excessivo de colunas.')
            if not headers:raise ValueError('Aba '+name+' sem cabeçalho. Campos: '+', '.join(SCHEMA[name])+'.')
            if any(not isinstance(h,str) for h in headers) or len(set(headers))!=len(headers):
                raise ValueError('Cabeçalho inválido ou duplicado em '+name+'.')
            missing=set(SCHEMA[name])-set(headers);extra=set(headers)-set(SCHEMA[name])-DERIVED[name]
            if missing or extra:
                raise ValueError(name+': '+('campos ausentes: '+', '.join(sorted(missing))+'. ' if missing else '')+('campos incompatíveis: '+', '.join(sorted(extra))+'.' if extra else ''))
            tables[name]=[]
            for line,cells in enumerate(records,2):
                total_cells+=len(cells)
                if total_cells>MAX_CELLS or line>MAX_ROWS+1:raise ValueError('Limites de linhas ou células excedidos.')
                if not any(c.value is not None for c in cells):continue
                total_rows+=1
                if total_rows>MAX_ROWS:raise ValueError('Limite de 5.000 registros por arquivo excedido.')
                record={};row_errors=[]
                for index,cell in enumerate(cells):
                    field=headers[index] if index<len(headers) else ''
                    if cell.data_type in ('f','e'):
                        row_errors.append((field or 'coluna extra','Fórmulas e erros de célula não são permitidos.'));continue
                    if not field:
                        if cell.value is not None:row_errors.append(('coluna extra','Conteúdo sem cabeçalho.'))
                        continue
                    if field not in SCHEMA[name]:continue
                    try:
                        if field in DATE_FIELDS:value=_date_value(cell.value,book.epoch)
                        else:
                            if field=='codigo' and cell.value is not None and not isinstance(cell.value,str):raise ValueError('O código deve ser texto, preservando seus zeros e identificador.')
                            value='' if cell.value is None else str(cell.value).strip()
                            # Own export escapes formula-like text; restore it as inert text.
                            if value[:1]=="'" and value[1:2] in ('=','+','-','@'):value=value[1:]
                            if len(value)>(1000 if field in ('descricao','observacoes') else 250):raise ValueError('Texto excede o limite do campo.')
                        record[field]=value
                    except ValueError as error:row_errors.append((field,str(error)))
                for field in SCHEMA[name]:record.setdefault(field,'')
                tables[name].append({'line':line,'record':record})
                errors.extend({'sheet':name,'line':line,'code':record.get('codigo',''),'field':field,'message':message} for field,message in row_errors)
        if not total_rows:raise ValueError('O arquivo não contém registros para analisar.')
    except ValueError:raise
    except Exception:raise ValueError('Arquivo XLSX corrompido ou estrutura não suportada.') from None
    finally:book.close()
    return tables,errors


def compare_upload(store, current, tables, mode, parse_errors=()):
    if mode not in ('new','upsert'):raise ValueError('Modo de importação inválido.')
    candidate=deepcopy(current);errors=list(parse_errors);changes=[];summary={};outcomes={}
    parse_error_lines={(e['sheet'],e['line']) for e in parse_errors}
    indexes={sheet:{r['codigo']:r for r in rows} for sheet,rows in candidate.items()}
    for sheet,entries in tables.items():
        counts=dict(found=len(entries),added=0,updated=0,unchanged=0,ignored=0,invalid=0)
        summary[sheet]=counts;seen=set()
        for entry in entries:
            row=entry['record'];code=row['codigo'];line=entry['line']
            if code in seen:
                errors.append(dict(sheet=sheet,line=line,code=code,field='codigo',message='Código duplicado no arquivo.'))
                continue
            seen.add(code)
            if (sheet,line) in parse_error_lines:continue
            try:store.validate({sheet:[row]},relationships=False)
            except (ValueError,TypeError) as error:
                errors.append(dict(sheet=sheet,line=line,code=code,field='',message=str(error)));continue
            old=indexes[sheet].get(code)
            if old is not None and mode=='new':counts['ignored']+=1;outcomes[sheet,line]='ignored';continue
            if old is not None and all(str(old.get(k,''))==row[k] for k in SCHEMA[sheet]):counts['unchanged']+=1;outcomes[sheet,line]='unchanged';continue
            kind='updated' if old is not None else 'added';counts[kind]+=1
            outcomes[sheet,line]=kind
            fields=[dict(field=k,before=old.get(k,'') if old else '',after=row[k]) for k in SCHEMA[sheet] if k!='codigo' and (old is None or old.get(k,'')!=row[k])]
            changes.append(dict(sheet=sheet,line=line,code=code,kind=kind,fields=fields))
            indexes[sheet][code]={**(old or {}),**row}
    for sheet,records in indexes.items():candidate[sheet]=list(records.values())
    for sheet,field,target in REFERENCES:
        valid=set(indexes[target])
        for entry in tables.get(sheet,[]):
            row=entry['record']
            if row[field] not in valid:errors.append(dict(sheet=sheet,line=entry['line'],code=row['codigo'],field=field,message='Referência inexistente em '+target+'.'))
    invalid_lines={(e['sheet'],e['line']) for e in errors}
    for sheet,line in invalid_lines:
        if (sheet,line) in outcomes:summary[sheet][outcomes[sheet,line]]-=1
    changes=[change for change in changes if (change['sheet'],change['line']) not in invalid_lines]
    for sheet,counts in summary.items():counts['invalid']=len({line for name,line in invalid_lines if name==sheet})
    if not errors:
        try:store.validate(candidate)
        except ValueError as error:errors.append(dict(sheet='Inventário',line=0,code='',field='',message=str(error)))
    totals={key:sum(s[key] for s in summary.values()) for key in ('found','added','updated','unchanged','ignored','invalid')}
    return candidate,dict(sheets=summary,totals=totals,errors=errors,changes=changes,can_confirm=not errors and bool(changes))
