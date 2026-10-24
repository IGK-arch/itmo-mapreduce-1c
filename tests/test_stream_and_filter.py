"""Boundary and semantic checks that matter for a chunked CSV implementation."""
import csv
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python-packages'))
sys.path.insert(0, str(ROOT / 'src'))
from vacancy_lab.mapreduce import ChunkStream, belongs_to_variant, map_batch


class BoundaryTests(unittest.TestCase):
    def test_utf8_quotes_and_newlines_across_three_byte_chunks(self):
        data = 'name,note\r\n"Программист 1С","строка 1\nстрока ""2"""\r\n'.encode()
        raw = ChunkStream(io.BytesIO(data), 3)
        reader = csv.DictReader(io.TextIOWrapper(io.BufferedReader(raw), encoding='utf-8', newline=''))
        self.assertEqual(list(reader), [{'name': 'Программист 1С', 'note': 'строка 1\nстрока "2"'}])
        self.assertEqual(raw.bytes_read, len(data))
        self.assertLessEqual(raw.max_read, 3)

    def test_variant_does_not_accept_accountants_consultants_or_bitrix(self):
        cases = [
            ('Программист 1С', 'Программист, разработчик', True),
            ('1C Developer', 'Программист, разработчик', True),
            ('Бухгалтер 1С', 'Бухгалтер', False),
            ('Консультант 1С', 'Программист, разработчик', False),
            ('Программист 1С-Битрикс', 'Программист, разработчик', False),
            ('Java-разработчик', 'Программист, разработчик', False),
            ('Java Developer (разработка новой технологии 1С:Предприятие.Элемент)',
             'Программист, разработчик', False),
            ('Программист 1С\\Python Junior', 'Программист, разработчик', True),
        ]
        for name, role, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(belongs_to_variant({'name': name, 'role': role}), expected)

    def test_repeated_skill_is_not_an_extra_skill_or_a_self_pair(self):
        row = {'source': 'test', 'vacancy_id': '1', 'name': 'Программист 1С',
               'role': 'Программист, разработчик', 'key_skills': ' SQL; SQL; 1С; Git; '}
        counts, hist, ids, emitted = map_batch([row], 'optimized')
        self.assertEqual(dict(hist), {3: 1})
        self.assertEqual(dict(emitted), {1: 3, 2: 3, 3: 1})
        self.assertEqual(counts[(2, 'git', 'sql')], 1)
        self.assertEqual(counts[(3, '1с', 'git', 'sql')], 1)
        self.assertNotIn((2, 'sql', 'sql'), counts)


if __name__ == '__main__':
    unittest.main()
