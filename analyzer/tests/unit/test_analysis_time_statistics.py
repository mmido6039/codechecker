# -------------------------------------------------------------------------
#
#  Part of the CodeChecker project, under the Apache License v2.0 with
#  LLVM Exceptions. See LICENSE for license information.
#  SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#
# -------------------------------------------------------------------------

"""
Test the collection of the analysis time of the translation units.
"""


import tempfile
import unittest

from codechecker_analyzer.analysis_manager import \
    SLOWEST_TU_COUNT, collect_duration_statistics, worker_result_handler


def create_metadata(*analyzers):
    """ Create a metadata dictionary for the given analyzers. """
    return {
        'result_source_files': {},
        'analyzers': {
            analyzer: {
                'analyzer_statistics': {
                    'failed': 0,
                    'failed_sources': [],
                    'successful': 0,
                    'successful_sources': [],
                    'version': 'x.y.z'}}
            for analyzer in analyzers}}


def create_result(analyzer, source, duration, returncode=0, skipped=False):
    """ Create a single analysis result of a worker process. """
    return (returncode, skipped, False, analyzer, source + '.plist', source,
            duration)


class AnalysisTimeStatisticsTest(unittest.TestCase):
    """
    Test that the analysis time of the translation units is measured and
    summarized per analyzer.
    """

    def test_duration_statistics(self):
        """ The summary of the durations is calculated correctly. """
        stats = collect_duration_statistics(
            [('a.cpp', 1.0), ('b.cpp', 4.0), ('c.cpp', 1.0)])

        self.assertEqual(stats['total'], 6.0)
        self.assertEqual(stats['min'], 1.0)
        self.assertEqual(stats['max'], 4.0)
        self.assertEqual(stats['avg'], 2.0)
        self.assertEqual(stats['slowest'][0],
                         {'file': 'b.cpp', 'duration': 4.0})

    def test_no_duration_statistics(self):
        """ No statistics are calculated if nothing was analyzed. """
        self.assertIsNone(collect_duration_statistics([]))

    def test_slowest_translation_units_are_limited(self):
        """ Only the slowest translation units are kept. """
        stats = collect_duration_statistics(
            [(f'{i}.cpp', float(i)) for i in range(SLOWEST_TU_COUNT + 10)])

        slowest = stats['slowest']
        self.assertEqual(len(slowest), SLOWEST_TU_COUNT)

        # The slowest translation units come first.
        durations = [tu['duration'] for tu in slowest]
        self.assertEqual(durations, sorted(durations, reverse=True))
        self.assertEqual(slowest[0]['file'],
                         f'{SLOWEST_TU_COUNT + 9}.cpp')

    def test_durations_land_in_metadata(self):
        """
        The analysis time of the translation units is collected per analyzer
        and stored in the metadata.
        """
        metadata = create_metadata('clangsa', 'clang-tidy')
        results = [
            create_result('clangsa', 'a.cpp', 2.0),
            create_result('clangsa', 'b.cpp', 6.0),
            create_result('clang-tidy', 'a.cpp', 1.0),
            # A failed analysis takes time too.
            create_result('clang-tidy', 'b.cpp', 3.0, returncode=1)]

        with tempfile.TemporaryDirectory() as output_path:
            worker_result_handler(results, metadata, output_path)

        analyzers = metadata['analyzers']

        clangsa = analyzers['clangsa']['analyzer_statistics']['duration']
        self.assertEqual(clangsa['total'], 8.0)
        self.assertEqual(clangsa['max'], 6.0)
        self.assertEqual(clangsa['avg'], 4.0)
        self.assertEqual([tu['file'] for tu in clangsa['slowest']],
                         ['b.cpp', 'a.cpp'])

        tidy = analyzers['clang-tidy']['analyzer_statistics']['duration']
        self.assertEqual(tidy['total'], 4.0)
        self.assertEqual(tidy['max'], 3.0)
        self.assertEqual([tu['file'] for tu in tidy['slowest']],
                         ['b.cpp', 'a.cpp'])

    def test_skipped_files_have_no_duration(self):
        """ Skipped translation units are left out of the statistics. """
        metadata = create_metadata('clangsa')
        results = [
            create_result('clangsa', 'a.cpp', 2.0),
            create_result('clangsa', 'b.cpp', 9.0, skipped=True)]

        with tempfile.TemporaryDirectory() as output_path:
            worker_result_handler(results, metadata, output_path)

        duration = \
            metadata['analyzers']['clangsa']['analyzer_statistics']['duration']
        self.assertEqual(duration['total'], 2.0)
        self.assertEqual(duration['max'], 2.0)
        self.assertEqual([tu['file'] for tu in duration['slowest']], ['a.cpp'])

    def test_analyzer_without_analyzed_file(self):
        """
        No duration statistics are stored for an analyzer which did not
        analyze anything.
        """
        metadata = create_metadata('clangsa', 'clang-tidy')

        with tempfile.TemporaryDirectory() as output_path:
            worker_result_handler(
                [create_result('clangsa', 'a.cpp', 2.0)],
                metadata, output_path)

        analyzers = metadata['analyzers']
        self.assertIn(
            'duration', analyzers['clangsa']['analyzer_statistics'])
        self.assertNotIn(
            'duration', analyzers['clang-tidy']['analyzer_statistics'])
