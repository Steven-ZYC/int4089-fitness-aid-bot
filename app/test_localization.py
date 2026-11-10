"""Catalog completeness and real dynamic translations, independent of hardware."""
import json
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from localization import MESSAGES, translate

class LocalizationTests(unittest.TestCase):
    def test_locales_have_matching_keys_and_parameters(self):
        self.assertEqual(set(MESSAGES), {'zh-CN','en','zh-HK'})
        source=MESSAGES['zh-CN']
        for locale, messages in MESSAGES.items():
            self.assertEqual(set(messages),set(source))
            for key, value in messages.items():
                self.assertTrue(value.strip(),(locale,key))
                self.assertEqual(sorted(re.findall(r'\{\d+\}',key)), sorted(re.findall(r'\{\d+\}',value)))

    def test_static_chinese_is_covered_except_native_language_names(self):
        texts=[]
        class Parser(HTMLParser):
            def handle_data(self,data):
                text=data.strip()
                if re.search('[\u4e00-\u9fff]',text):texts.append(text)
            def handle_starttag(self,tag,attrs):
                for attr,text in attrs:
                    if attr in ('aria-label','alt','title') and re.search('[\u4e00-\u9fff]',text or ''):texts.append(text)
        Parser().feed((Path(__file__).parent/'web/index.html').read_text(encoding='utf-8'))
        for text in texts:
            if text not in ('简体中文','繁體中文（香港）'):self.assertIn(text,MESSAGES['en'])

    def test_exercise_guides_are_translated(self):
        exercises=json.loads((Path(__file__).parent/'web/exercises.json').read_text(encoding='utf-8'))
        for item in exercises:
            labels=[item['name'],item['group'],*item['stages'],*[label for cue in item['cues'] for label in cue]]
            for label in labels:
                for locale in MESSAGES:self.assertIn(label,MESSAGES[locale])

    def test_dynamic_feedback_preserves_values(self):
        self.assertEqual(translate('深蹲 · 站立 · 第 3 次','en'),'Squat · Standing · Rep 3')
        self.assertEqual(translate('第 12 次：需要调整','en'),'Rep 12: Needs adjustment')
        self.assertEqual(translate('下蹲深度不足：最低膝角 115°，建议 ≤105°','en'),
                         'Squat too shallow: minimum knee angle 115°; target ≤105°')
        self.assertEqual(translate('设备与校准','zh-HK'),'設備與校準')

    def test_pipeline_waiting_overlays_follow_language(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        import numpy as np
        from pose_app import Pipeline, STATE
        from copy import deepcopy
        for locale in MESSAGES:
            for locked, key in ((False,'自动校正中：请短暂站直，双手自然下垂'),
                                (True,'未检测到人 — 请确保全身进入画面')):
                with self.subTest(locale=locale,locked=locked):
                    pipeline=Pipeline('test','squat',engine=Mock(infer=lambda _: (None,None)))
                    pipeline.language=locale
                    pipeline.orientation=SimpleNamespace(mode='0',angle=0,mirror=False,locked=locked,
                        update=lambda *args:None,transform=lambda frame:frame,state=lambda:{})
                    source=Mock(desc='test camera',seq=1)
                    reads=[]
                    def frame():
                        reads.append(True)
                        if len(reads)>1:pipeline.running=False
                        return np.zeros((480,640,3),dtype=np.uint8)
                    source.read=frame
                    rendered=[]
                    def capture(frame,items):
                        rendered.extend(item[0] for item in items)
                        return frame
                    with patch('pose_app.STATE',deepcopy(STATE)),patch('pose_app.open_source',return_value=source),patch('pose_app.draw_cn',side_effect=capture):
                        pipeline._run_pipeline()
                    self.assertEqual(rendered,[MESSAGES[locale][key]])

    def test_raw_protocol_diagnostics_are_not_translated(self):
        raw='# DETECT address=0x68 read_ok=0'
        for locale in MESSAGES:self.assertEqual(translate(raw,locale),raw)

if __name__=='__main__':unittest.main()
