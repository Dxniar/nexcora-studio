"""Компактные payload; полномочия проверяет обработчик и Repository."""
from dataclasses import dataclass
import re
from .catalog import get_service
from .models import STATUSES

SCOPES = {'nav':'n','service':'s','draft':'d','order':'o','preferences':'p','delete':'x','admin':'a','retry':'r'}
VERBS = {'go':'g','view':'v','start':'i','accept':'a','submit':'s','skip':'k','back':'b',
         'edit':'e','cancel':'c','replace':'r','resume':'u','set':'t','confirm':'y','keep':'n','list':'l','failures':'f'}
FIELDS = {'service':'s','description':'d','budget':'b','deadline':'t','name':'n'}


@dataclass(frozen=True)
class Action:
    scope: str
    entity_id: str = ''
    revision: int = 0
    verb: str = ''
    argument: str = ''


def valid(a):
    if a.scope not in SCOPES or a.verb not in VERBS or not 0<=a.revision<2**63: return False
    entity,verb,arg = a.entity_id,a.verb,a.argument
    if a.scope=='nav':
        return verb=='go' and entity in ('home','services','projects','workflow','contact','help','myorders','new','resume','delete') and (not arg or (entity=='myorders' and arg.isdecimal() and len(arg)<10))
    if a.scope=='service': return bool(get_service(entity)) and verb in ('view','start') and not arg
    if a.scope=='draft':
        if not re.fullmatch('[0-9a-f]{32}',entity): return False
        if verb=='edit': return arg in FIELDS
        if verb=='accept': return bool(get_service(arg))
        if verb=='replace': return not arg or bool(get_service(arg))
        return verb in ('submit','skip','back','cancel','resume') and not arg
    if a.scope=='delete': return bool(re.fullmatch('[0-9a-f]{32}',entity)) and verb in ('confirm','keep') and not arg
    if a.scope=='preferences': return entity in ('0','1') and verb=='set' and not arg
    if not entity.isdecimal() or len(entity)>19 or int(entity)>=2**63: return False
    if a.scope=='order': return int(entity)>0 and verb=='view' and not arg
    if a.scope=='retry': return int(entity)>0 and verb=='set' and not arg
    if a.scope=='admin':
        if verb=='list': return arg in (*STATUSES,'all')
        if verb=='failures': return not arg
        return int(entity)>0 and ((verb=='view' and not arg) or (verb=='set' and arg in STATUSES))
    return False


def encode_action(action):
    if not valid(action): raise ValueError('Invalid action')
    arg = FIELDS[action.argument] if action.scope=='draft' and action.verb=='edit' else action.argument
    value = '|'.join((SCOPES[action.scope],action.entity_id,str(action.revision),VERBS[action.verb],arg))
    if len(value.encode('utf-8'))>64: raise ValueError('Action is too long')
    return value


def decode_action(data):
    if not isinstance(data,str) or len(data.encode('utf-8'))>64: return None
    try:
        scope,entity,revision,verb,arg = data.split('|')
        if not revision.isdecimal() or len(revision)>19: return None
        scope = {v:k for k,v in SCOPES.items()}[scope]
        verb = {v:k for k,v in VERBS.items()}[verb]
        if scope=='draft' and verb=='edit': arg={v:k for k,v in FIELDS.items()}[arg]
        action=Action(scope,entity,int(revision),verb,arg)
        return action if valid(action) else None
    except (ValueError,KeyError): return None
