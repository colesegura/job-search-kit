#!/usr/bin/env python3
"""Offline consistency checks. No browser, network, or external action enforcement."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTION_NAMES = {'fill', 'upload', 'submit', 'email_application', 'followup',
                'create_account', 'contact_reference', 'contact_employer',
                'consent', 'purchase', 'accept_offer'}
STATUSES = {'prepared', 'blocked', 'incomplete', 'inquiry_sent', 'submitted', 'unknown_outcome'}
ROUTES = {'portal_application', 'email_application', 'general_application', 'inquiry'}
KINDS = {'portal_confirmation', 'sent_application', 'user_verified'}


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp missing')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('invalid timestamp') from None
    if result.tzinfo is None:
        raise ValueError('timestamp needs time zone')
    return result


def require(condition, message):
    if not condition:
        raise ValueError(message)


def index(rows, label):
    require(isinstance(rows, list), label + ' must be a list')
    result = {}
    for row in rows:
        require(isinstance(row, dict), label + ' entry must be an object')
        key = row.get('id')
        require(isinstance(key, str) and key.strip(), label + ' needs an ID')
        require(key not in result, label + ' duplicate ID: ' + key)
        result[key] = row
    return result


def authorized(grant, target, action, when, historical=False):
    if grant.get('revoked'):
        if not historical or when >= timestamp(grant.get('revoked_at')):
            return False
    return (target in grant['target_ids'] and action in grant['actions']
            and timestamp(grant['granted_at']) <= when < timestamp(grant['expires_at']))


def check_facts(ids, facts, when):
    require(isinstance(ids, list) and bool(ids), 'planned/used fact IDs required')
    for fid in ids:
        require(fid in facts, 'unknown fact ID')
        fact = facts[fid]
        require(fact.get('value') is not None, 'unverified fact: ' + fid)
        require(timestamp(fact['confirmed_at']) <= when, 'fact confirmed after action: ' + fid)
        if fact.get('expires_at'):
            require(when < timestamp(fact['expires_at']), 'expired fact: ' + fid)


def validate(data):
    require(data.get('schema_version') == 1, 'unsupported schema version')
    age = data.get('settings', {}).get('max_verification_age_days')
    require(type(age) in (int, float) and 0 < age <= 30, 'verification age must be in (0, 30] days')
    criteria = index(data.get('profile', {}).get('criteria'), 'criteria')
    for row in criteria.values():
        require(row.get('kind') in {'hard', 'preference', 'hypothesis', 'rejected', 'deferred'}, 'invalid criterion kind')
        require(row.get('statement') and row.get('source'), 'criterion needs statement and source')
    sources = index(data.get('sources'), 'sources')
    for row in sources.values():
        require(row.get('locator') and row.get('permitted_use'), 'source needs locator and permitted use')
    facts = index(data.get('facts'), 'facts')
    for row in facts.values():
        require(row.get('source_id') in sources, 'fact source not registered')
        if row.get('value') is not None:
            confirmed = timestamp(row.get('confirmed_at'))
            if row.get('expires_at'):
                require(timestamp(row['expires_at']) > confirmed, 'fact expiry precedes confirmation')
    grants = index(data.get('authorizations'), 'authorizations')
    opportunities = index(data.get('opportunities'), 'opportunities')
    keys = set()
    for row in opportunities.values():
        key = row.get('canonical_key')
        require(isinstance(key, str) and key.strip(), 'opportunity needs canonical key')
        require(key not in keys, 'duplicate canonical opportunity key')
        keys.add(key)
        require(row.get('employer') and row.get('role') and row.get('url'), 'opportunity identity incomplete')
        require(row.get('route') in ROUTES, 'invalid opportunity route')
        require(row.get('status') in {'current_opening', 'verified_route', 'closed', 'unverified'}, 'invalid opportunity status')
        if row.get('status') in {'current_opening', 'verified_route'}:
            timestamp(row.get('checked_at'))
    for row in grants.values():
        require(isinstance(row.get('target_ids'), list) and bool(row['target_ids']), 'authorization needs exact targets')
        require(all(t in opportunities for t in row['target_ids']), 'authorization references unknown target')
        require(isinstance(row.get('actions'), list) and bool(row['actions']), 'authorization actions required')
        require(all(a in ACTION_NAMES for a in row['actions']), 'unknown authorized action')
        require(row.get('user_instruction') and row.get('instruction_source'), 'authorization needs actual user instruction provenance')
        require(type(row.get('revoked')) is bool, 'authorization revocation must be boolean')
        if row['revoked']:
            require(timestamp(row.get('revoked_at')) >= timestamp(row.get('granted_at')), 'revocation timestamp required')
        require(timestamp(row.get('expires_at')) > timestamp(row.get('granted_at')), 'invalid authorization window')
    actions = index(data.get('actions'), 'actions')
    completed = set()
    for row in actions.values():
        target = row.get('target_id')
        require(target in opportunities, 'action references unknown target')
        require(row.get('action') in ACTION_NAMES, 'unknown action')
        require(row.get('status') in STATUSES, 'unknown action status')
        ids = row.get('authorization_ids', [])
        require(isinstance(ids, list) and all(g in grants for g in ids), 'unknown authorization reference')
        require(isinstance(row.get('fact_ids', []), list) and all(f in facts for f in row.get('fact_ids', [])), 'unknown fact reference')
        if row['status'] not in {'submitted', 'inquiry_sent', 'incomplete', 'unknown_outcome'}:
            continue
        when = timestamp(row.get('performed_at'))
        require(any(authorized(grants[g], target, row['action'], when, historical=True) for g in ids), 'performed action lacks matching authorization')
        check_facts(row.get('fact_ids'), facts, when)
        if row['status'] in {'incomplete', 'unknown_outcome'}:
            continue
        receipt = row.get('receipt')
        require(isinstance(receipt, dict) and receipt.get('kind') in KINDS and receipt.get('evidence'), 'observed receipt required')
        require(timestamp(receipt.get('observed_at')) >= when, 'receipt predates action')
        if row['status'] == 'inquiry_sent':
            require(row['action'] in {'followup', 'email_application'}, 'inquiry needs email action')
            continue
        require(row['action'] in {'submit', 'email_application'}, 'submission needs application action')
        route = opportunities[target]['route']
        require(route != 'inquiry', 'inquiry cannot count as application')
        require(not row.get('applicant_only_pending', True), 'applicant-only step remains')
        require(row.get('remaining_required_steps') == [], 'required application steps remain')
        if row['action'] == 'email_application':
            require(route in {'email_application', 'general_application'}, 'email action route mismatch')
            require(receipt['kind'] in {'sent_application', 'user_verified'}, 'email needs sent evidence')
        else:
            require(route in {'portal_application', 'general_application'}, 'portal action route mismatch')
            require(receipt['kind'] in {'portal_confirmation', 'user_verified'}, 'portal needs confirmation')
        key = opportunities[target]['canonical_key']
        require(key not in completed, 'duplicate completed application')
        completed.add(key)
    for row in index(data.get('coverage'), 'coverage').values():
        require(row.get('status') in {'unsearched', 'partial', 'screened'}, 'invalid coverage status')
        require(row.get('scope'), 'coverage scope required')
        require(isinstance(row.get('required_sources'), list) and isinstance(row.get('checked_sources'), list)
                and isinstance(row.get('gaps'), list), 'coverage source lists/gaps required')
        if row['status'] == 'screened':
            timestamp(row.get('checked_at'))
            require(bool(row['required_sources']) and set(row['required_sources']) <= set(row['checked_sources'])
                    and not row['gaps'], 'screened coverage has incomplete procedure')
    return completed


def preflight(data, target, action, now=None, fact_ids=None):
    validate(data)
    now = now or datetime.now(timezone.utc)
    require(action in ACTION_NAMES, 'unknown action')
    opportunities = index(data['opportunities'], 'opportunities')
    require(target in opportunities, 'unknown target')
    opp = opportunities[target]
    require(opp['status'] in {'current_opening', 'verified_route'}, 'route not currently verified')
    checked = timestamp(opp['checked_at'])
    require(checked <= now <= checked + timedelta(days=data['settings']['max_verification_age_days']), 'stale or future verification')
    require(any(authorized(g, target, action, now) for g in data['authorizations']), 'no current matching authorization')
    if action in {'submit', 'email_application'}:
        require(opp['route'] != 'inquiry', 'inquiry is not an application route')
        valid = {'portal_application', 'general_application'} if action == 'submit' else {'email_application', 'general_application'}
        require(opp['route'] in valid, 'action does not match application route')
        require(not any(a['target_id'] == target and a['status'] in {'submitted', 'unknown_outcome'} for a in data['actions']), 'already submitted or unresolved prior attempt')
    planned = [a for a in data['actions'] if a['target_id'] == target and a['status'] in {'prepared', 'blocked', 'incomplete'}]
    require(bool(planned), 'prepared action with reviewed steps required')
    plan = planned[-1]
    if action in {'submit', 'email_application'}:
        require(plan.get('applicant_only_pending') is False and plan.get('remaining_required_steps') == [], 'applicant/required steps remain')
    check_facts(fact_ids if fact_ids is not None else plan.get('fact_ids'), index(data['facts'], 'facts'), now)
    return True


def initialize(directory):
    # Exclusive directory creation prevents overwriting any existing private workspace.
    directory.mkdir(parents=True, exist_ok=False)
    for name in ('search.json', 'current.md'):
        (directory / name).write_text((ROOT / 'templates' / name).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=ROOT / 'private')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('init', 'validate', 'summary'):
        sub.add_parser(command)
    flight = sub.add_parser('preflight')
    flight.add_argument('target')
    flight.add_argument('--action', choices=sorted(ACTION_NAMES), required=True)
    flight.add_argument('--fact-id', action='append')
    args = parser.parse_args()
    try:
        if args.command == 'init':
            initialize(args.workspace)
            print('Private workspace initialized. No permissions granted.')
            return
        data = json.loads((args.workspace / 'search.json').read_text())
        completed = validate(data)
        if args.command == 'preflight':
            preflight(data, args.target, args.action, fact_ids=args.fact_id)
            print('Recorded preflight checks pass. Observe the form and verify live authority before action.')
        elif args.command == 'summary':
            print(json.dumps({'recorded_completed_applications': len(completed),
                              'recorded_inquiries': sum(a['status'] == 'inquiry_sent' for a in data['actions']),
                              'recorded_unfinished': sum(a['status'] in {'blocked', 'incomplete', 'unknown_outcome'} for a in data['actions']),
                              'opportunities': len(data['opportunities'])}))
        else:
            print('Tracker consistency checks pass. Recorded evidence has not been independently verified.')
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        # Do not print arbitrary source values from JSON parsing or OS errors.
        if type(exc) is ValueError:
            print('Blocked: ' + str(exc))
        else:
            print('Blocked: invalid or inaccessible workspace (' + type(exc).__name__ + ')')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
