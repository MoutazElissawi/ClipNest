"""Recorder settings use each encoder's own option types."""
import os

def video_encoder_settings(settings):
    label = settings['encoder']
    result = dict(rate_control='CBR', bitrate=settings['bitrate'], keyint_sec=2)
    if label.startswith('CPU'):
        result.update(profile='high', preset='veryfast')
    elif label.startswith('NVIDIA'):
        result.update(profile='main' if 'AV1' in label else 'high',
                      preset=settings.get('nvenc_preset', 'p4'), tune='hq',
                      multipass='disabled', bf=2, lookahead=False, adaptive_quantization=False)
    elif label.startswith('AMD'):
        if os.name == 'nt':
            result.update(profile='high' if 'H.264' in label else 'main', preset='balanced')
        else:
            # VAAPI requires integer FFmpeg profiles; let OBS select its device.
            result.update(profile=100 if 'H.264' in label else 1 if 'HEVC' in label else 0, bf=0)
    return result
