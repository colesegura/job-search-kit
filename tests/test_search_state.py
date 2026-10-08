import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


state = load('search_state')
public = load('check_public')
NOW = datetime(2030, 1, 3, tzinfo=timezone.utc)


def fixture():
    data = json.loads((ROOT / 'templates/search.json').read_text())
    data['sources'] = [{'id': 's1', 'locator': 'private/user-interview.md', 'permitted_use': 'candidate facts'}]
    data['facts'] = [{'id': 'f1', 'value': 'synthetic verified fact', 'source_id': 's1',
                      'confirmed_at': '2030-01-01T00:00:00Z', 'expires_at': None}]
    data['opportunities'] = [{'id': 'o1', 'canonical_key': 'example:REQ1', 'employer': 'Example Employer',
                             'role': 'Example Role', 'url': 'https://employer.example.invalid/jobs/REQ1',
                             'route': 'portal_application', 'status': 'current_opening',
                             'checked_at': '2030-01-02T00:00:00Z', 'uncertainties': []}]
    data['authorizations'] = [{'id': 'g1', 'target_ids': ['o1'], 'actions': ['fill', 'upload', 'submit'],
                              'granted_at': '2030-01-01T00:00:00Z', 'expires_at': '2030-01-09T00:00:00Z',
                              'user_instruction': 'Synthetic permission for the listed application actions.',
                              'instruction_source': 'private/synthetic-instruction.md', 'revoked': False}]
    data['actions'] = [{'id': 'a1', 'target_id': 'o1', 'action': 'submit', 'status': 'prepared',
                        'performed_at': None, 'authorization_ids': ['g1'], 'fact_ids': ['f1'],
                        'applicant_only_pending': False, 'remaining_required_steps': [], 'receipt': None}]
    return data


def submitted():
    data = fixture()
    data['actions'][0].update(status='submitted', performed_at='2030-01-03T00:00:00Z',
                              receipt={'kind': 'portal_confirmation', 'observed_at': '2030-01-03T00:01:00Z',
                                       'evidence': 'Synthetic application confirmation'})
    return data


class SearchTests(unittest.TestCase):
    def test_empty_template_is_not_completed_work(self):
        self.assertEqual(state.validate(json.loads((ROOT / 'templates/search.json').read_text())), set())

    def test_preflight_authorized_submission(self):
        self.assertTrue(state.preflight(fixture(), 'o1', 'submit', NOW))

    def test_no_followup_authority_from_application_permission(self):
        with self.assertRaises(ValueError):
            state.preflight(fixture(), 'o1', 'followup', NOW)

    def test_wrong_target_and_wrong_action_are_blocked(self):
        for target, action in [('other', 'submit'), ('o1', 'create_account')]:
            with self.subTest(target=target, action=action), self.assertRaises(ValueError):
                state.preflight(fixture(), target, action, NOW)

    def test_expired_and_revoked_authority(self):
        for field, value in [('expires_at', '2030-01-02T00:00:00Z'), ('revoked', True)]:
            data = fixture()
            data['authorizations'][0][field] = value
            data['authorizations'][0]['revoked_at'] = '2030-01-02T00:00:00Z'
            with self.subTest(field=field), self.assertRaises(ValueError):
                state.preflight(data, 'o1', 'submit', NOW)

    def test_revocation_does_not_erase_valid_history(self):
        data = submitted()
        data['authorizations'][0].update(revoked=True, revoked_at='2030-01-04T00:00:00Z')
        self.assertEqual(len(state.validate(data)), 1)
        data['authorizations'][0]['revoked_at'] = '2030-01-02T00:00:00Z'
        with self.assertRaises(ValueError):
            state.validate(data)

    def test_unknown_and_expired_fact(self):
        for changes in [{'value': None}, {'expires_at': '2030-01-02T00:00:00Z'}]:
            data = fixture()
            data['facts'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                state.preflight(data, 'o1', 'submit', NOW)

    def test_stale_and_future_verification(self):
        for date in ['2029-01-01T00:00:00Z', '2030-01-04T00:00:00Z']:
            data = fixture()
            data['opportunities'][0]['checked_at'] = date
            with self.subTest(date=date), self.assertRaises(ValueError):
                state.preflight(data, 'o1', 'submit', NOW)

    def test_receipt_and_completion_requirements(self):
        for changes in [{'receipt': None}, {'applicant_only_pending': True}, {'remaining_required_steps': ['full packet']}]:
            data = submitted()
            data['actions'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                state.validate(data)

    def test_incomplete_packet_excluded(self):
        data = submitted()
        data['actions'][0].update(status='incomplete', remaining_required_steps=['required packet'])
        self.assertEqual(state.validate(data), set())

    def test_inquiry_excluded_from_completed_applications(self):
        data = submitted()
        data['opportunities'][0]['route'] = 'inquiry'
        data['authorizations'][0]['actions'].append('followup')
        data['actions'][0].update(action='followup', status='inquiry_sent')
        self.assertEqual(state.validate(data), set())
        data['actions'][0].update(action='submit', status='submitted')
        with self.assertRaises(ValueError):
            state.validate(data)

    def test_email_route_needs_email_permission_and_receipt(self):
        data = submitted()
        data['opportunities'][0]['route'] = 'email_application'
        data['actions'][0]['action'] = 'email_application'
        data['actions'][0]['receipt']['kind'] = 'sent_application'
        with self.assertRaises(ValueError):
            state.validate(data)
        data['authorizations'][0]['actions'].append('email_application')
        self.assertEqual(len(state.validate(data)), 1)

    def test_duplicate_application_not_counted_twice(self):
        data = submitted()
        duplicate = copy.deepcopy(data['actions'][0])
        duplicate['id'] = 'a2'
        data['actions'].append(duplicate)
        with self.assertRaises(ValueError):
            state.validate(data)

    def test_unknown_outcome_prevents_retry(self):
        data = submitted()
        data['actions'][0]['status'] = 'unknown_outcome'
        plan = fixture()['actions'][0]
        plan['id'] = 'a2'
        data['actions'].append(plan)
        with self.assertRaises(ValueError):
            state.preflight(data, 'o1', 'submit', NOW)

    def test_pending_signature_blocks_submit_but_not_authorized_fill(self):
        data = fixture()
        data['actions'][0]['applicant_only_pending'] = True
        with self.assertRaises(ValueError):
            state.preflight(data, 'o1', 'submit', NOW)
        self.assertTrue(state.preflight(data, 'o1', 'fill', NOW))

    def test_registered_coverage_is_not_screened(self):
        data = fixture()
        data['coverage'] = [{'id': 'c1', 'scope': 'Synthetic corridor', 'status': 'screened',
                             'required_sources': ['employer', 'government'], 'checked_sources': ['employer'],
                             'checked_at': '2030-01-02T00:00:00Z', 'gaps': []}]
        with self.assertRaises(ValueError):
            state.validate(data)
        data['coverage'][0]['status'] = 'partial'
        state.validate(data)

    def test_init_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'private'
            state.initialize(path)
            original = (path / 'search.json').read_bytes()
            with self.assertRaises(FileExistsError):
                state.initialize(path)
            self.assertEqual((path / 'search.json').read_bytes(), original)

    def test_public_scanner_detects_real_email_not_synthetic(self):
        self.assertTrue(public.findings('synthetic.txt', 'person' + '@' + 'real.example.com'))
        self.assertEqual(public.findings('synthetic.txt', 'person@example.invalid'), [])

    def test_public_scanner_rejects_unapproved_file(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'candidate.txt').write_text('private candidate data')
            self.assertTrue(public.scan(Path(temp)))


if __name__ == '__main__':
    unittest.main()
