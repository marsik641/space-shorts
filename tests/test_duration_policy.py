"""Границы 30-секундного формата: preflight и длительность дорожек."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
# В старом worktree шлюз может быть только в основной копии.
sys.path.append(str(ROOT.parents[1]/'tools'))
import check_episode
import qa


class DurationPolicy(unittest.TestCase):
    def check_frames(self,frames):
        scratch=ROOT/'out'/'duration_tests';scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch)as d:
            assert Path(d).resolve().is_relative_to(scratch.resolve())
            root=Path(d);ep=root/'episodes'/'ep999_boundary';ep.mkdir(parents=True)
            duration=frames/60
            data={'id':ep.name,'languages':['en'],'format':{'w':1080,'h':1920,'fps':60},
                  'edit':[{'shot':'v1','frames':frames}],'overlays':{'en':[]}}
            (ep/'episode.json').write_text(json.dumps(data),encoding='utf-8')
            (ep/'shots_9x16.py').write_text('SHOTS = '+repr({'v1':frames}),encoding='utf-8')
            (ep/'script_9x16.json').write_text(json.dumps({'duration_s':duration,'voices':{'en':{}},
                'segments':[{'at':.1,'shot':'v1','en':'A real object.'}]}),encoding='utf-8')
            (ep/'music_cues.json').write_text(json.dumps({'duration_s':duration,'key':'A','chords':[]}),encoding='utf-8')
            with patch.object(check_episode,'REPO',str(root)),patch.object(check_episode,'chord_parser',return_value=None),contextlib.redirect_stdout(io.StringIO()):
                return check_episode.main(str(ep/'episode.json'))

    def test_target_29_5_seconds(self):self.assertEqual(self.check_frames(1770),0)
    def test_last_safe_frame(self):self.assertEqual(self.check_frames(1799),0)
    def test_30_seconds_needs_aac_headroom(self):self.assertEqual(self.check_frames(1800),1)
    def test_over_30_rejected(self):self.assertEqual(self.check_frames(1801),1)

    def test_encoded_audio_limit(self):
        fmt={'w':1080,'h':1920,'fps':60}
        line='VIDEO size (1080, 1920) fps 60 frames 1770 seconds 29.5\n'
        self.assertTrue(qa.verdict(line+'AUDIO seconds 29.504',fmt,1770)[0])
        self.assertFalse(qa.verdict(line+'AUDIO seconds 30.016',fmt,1770)[0])


if __name__=='__main__':unittest.main()
