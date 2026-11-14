import unittest
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

from pipelines.audio_production import gain_plan, validate_options
import workflow


class NormalizationTests(unittest.TestCase):
    def test_off_does_not_change_gain(self):
        self.assertEqual(gain_plan('off', {})['gain_db'], 0)

    def test_loudness_gain_is_capped_instead_of_limiting(self):
        plan = gain_plan('loudness', {'integrated_lufs': -24, 'true_peak_dbtp': -2},
                         target_lufs=-16, true_peak=-1.5)
        self.assertAlmostEqual(plan['gain_db'], 0.5)
        self.assertTrue(plan['gain_limited_by_headroom'])
        self.assertFalse(plan['limiting'])

    def test_loudness_attenuates_a_hot_mix(self):
        plan = gain_plan('loudness', {'integrated_lufs': -10, 'true_peak_dbtp': -0.1})
        self.assertAlmostEqual(plan['gain_db'], -6)

    def test_peak_uses_sample_peak(self):
        self.assertEqual(gain_plan('peak', {'sample_peak_dbfs': -8}, peak_db=-1)['gain_db'], 7)

    def test_silence_cannot_be_loudness_normalized(self):
        with self.assertRaisesRegex(ValueError, 'silent or too short'):
            gain_plan('loudness', {'integrated_lufs': None, 'true_peak_dbtp': None})

    def test_nonfinite_targets_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_options(SimpleNamespace(target_lufs=float('nan')))

    def test_limiting_needs_explicit_loudness_mode(self):
        with self.assertRaisesRegex(ValueError, 'requires --normalize loudness'):
            validate_options(SimpleNamespace(allow_limiting=True, normalize='off'))

    def test_preview_upload_rejected_before_job_creation(self):
        with self.assertRaisesRegex(ValueError, 'local outputs'):
            workflow.execute(SimpleNamespace(preset='preview', upload=True))


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg and ffprobe required')
class NativeRateTests(unittest.TestCase):
    def test_peak_target_uses_native_samples_including_96khz_exports(self):
        import numpy as np
        import soundfile as sf
        from pipelines.audio_production import export_audio
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for source_rate in (44100, 96000):
                with self.subTest(source_rate=source_rate):
                    source = folder / f'{source_rate}.wav'
                    samples = 0.15 * np.sin(2 * np.pi * 18000 * np.arange(source_rate) / source_rate)
                    sf.write(source, samples, source_rate, subtype='FLOAT')
                    master, report = export_audio([source], folder / str(source_rate),
                        sample_rate=96000, normalize='peak', peak_db=-2)
                    exported, rate = sf.read(master)
                    sample_peak = 20 * np.log10(np.max(np.abs(exported)))
                    self.assertEqual(rate, 96000)
                    self.assertEqual(report['after']['analysis_sample_rate'], 96000)
                    self.assertAlmostEqual(sample_peak, -2, places=2)


if __name__ == '__main__':
    unittest.main()
