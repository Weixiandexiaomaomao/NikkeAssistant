"""用国服截图回放关键识别，防止把可领奖励页面误认成空状态。"""
import json
import sys
import unittest
from pathlib import Path

try:
    import cv2
except ImportError:
    cv2 = None
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import compile_steps


def read_image(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def score(name, capture):
    if cv2 is None or not (ROOT / 'captures' / (capture + '.png')).is_file():
        raise unittest.SkipTest('Private screenshot fixtures/OpenCV are optional and not distributed')
    spec = json.loads((ROOT / 'resource' / 'cn_manifest.json').read_text())[name]
    image = read_image(ROOT / 'captures' / (capture + '.png'))
    h, w = image.shape[:2]
    scale = 720 / min(w, h)
    image = cv2.resize(image, (round(w * scale), round(h * scale)))
    x, y, rw, rh = spec['roi']
    area = image[y:y + rh, x:x + rw]
    template = read_image(ROOT / 'resource' / 'image' / spec['template'])
    method = cv2.TM_SQDIFF_NORMED if spec['method'] == 10001 else spec['method']
    result = cv2.matchTemplate(area, template, method)
    value = 1 - result.min() if spec['method'] == 10001 else result.max()
    return float(value), spec['threshold']


class ResourceTests(unittest.TestCase):
    def test_empty_state_requires_actual_text(self):
        hit, threshold = score('defense_empty', 'defense_after_reward')
        self.assertGreaterEqual(hit, threshold)
        for image in ('defense', 'defense_validation'):
            hit, threshold = score('defense_empty', image)
            self.assertLess(hit, threshold, image)

    def test_dimmed_background_does_not_trigger_click(self):
        hit, threshold = score('defense_title', 'defense')
        self.assertGreaterEqual(hit, threshold)
        hit, threshold = score('defense_title', 'defense_reward')
        self.assertLess(hit, threshold)
        hit, threshold = score('lobby', 'lobby')
        self.assertGreaterEqual(hit, threshold)
        for image in ('mailbox', 'friends', 'defense'):
            hit, threshold = score('lobby', image)
            self.assertLess(hit, threshold, image)

    def test_disabled_buttons_match(self):
        for name, capture in [('mail_disabled', 'mailbox'), ('friend_disabled', 'friends')]:
            hit, threshold = score(name, capture)
            self.assertGreaterEqual(hit, threshold)

    def test_graphs_have_only_verified_terminal(self):
        for path in (ROOT / 'pipelines').glob('*.json'):
            graph = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(graph['Entry'].get('action', 'DoNothing'), 'DoNothing')
            for name, node in graph.items():
                for target in node.get('next', []):
                    self.assertIn(target, graph)
                if not node.get('next'):
                    self.assertEqual(name, 'Done')
                    self.assertEqual(node['action'], 'DoNothing')
                    self.assertEqual(node['recognition'], 'OCR')
                    self.assertEqual(node['expected'], ['^大厅$'])
                    self.assertEqual(node['roi'], [280,1180,180,100])

    def test_custom_entry_cannot_click_before_recognition(self):
        step = {'action': 'check', 'template': 'cn/lobby.png', 'roi': [0, 0, 50, 50], 'threshold': 0.9}
        graph = compile_steps([step])
        self.assertEqual(graph['Entry']['next'], ['Step0'])
        self.assertNotIn('action', graph['Entry'])
        with self.assertRaises(ValueError):
            compile_steps([{**step, 'action': 'click'}])


if __name__ == '__main__':
    unittest.main()
