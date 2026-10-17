import { describe, expect, it } from 'vitest';
import { cameraName, detectionsForCamera, frameForCamera, objectColor } from '../camera';
import type { CameraFrame, Detection, Snapshot } from '../types';
import { colors } from '../ui';

const frame = (camera_id?: string): CameraFrame => ({camera_id, frame_id: 7, timestamp: 1, run_id: 'r', width: 960, height: 540, url: '/api/frame', age_ms: 0});
const detection = (extra: Partial<Detection>): Detection => ({bbox: [0, 0, 1, 1], track_id: 1, sku: 'PEX-001', confidence: 0.9, ...extra});
const snapshot = (extra: Partial<Snapshot>) => ({frame: null, detections: [], ...extra}) as Snapshot;

describe('frameForCamera', () => {
  it('returns nothing without a snapshot', () => {
    expect(frameForCamera(null, 'lane')).toBeNull();
  });
  it('picks the camera from a grouped snapshot and never substitutes another view', () => {
    const s = snapshot({frames: {lane: frame('lane')}, frame: frame('lane')});
    expect(frameForCamera(s, 'lane')?.camera_id).toBe('lane');
    expect(frameForCamera(s, 'overhead')).toBeNull();
  });
  it('treats a legacy single frame without a camera ID as the lane camera', () => {
    const s = snapshot({frame: frame()});
    expect(frameForCamera(s, 'lane')).not.toBeNull();
    expect(frameForCamera(s, 'overhead')).toBeNull();
  });
});

describe('detectionsForCamera', () => {
  it('splits detections by camera, defaulting to the lane camera', () => {
    const s = snapshot({detections: [detection({camera: 'overhead'}), detection({}), detection({camera: 'lane'})]});
    expect(detectionsForCamera(s, 'lane')).toHaveLength(2);
    expect(detectionsForCamera(s, 'overhead')).toHaveLength(1);
    expect(detectionsForCamera(null, 'lane')).toEqual([]);
  });
});

describe('objectColor', () => {
  it('uses fixed colors for objects outside the lane and unresolved products', () => {
    expect(objectColor(detection({state: 'OUTSIDE'}))).toBe('#8fa3bf');
    expect(objectColor(detection({sku: null}))).toBe('#ff8293');
  });
  it('gives one physical object the same palette color every frame', () => {
    const a = objectColor(detection({object_id: 'obj-12', track_id: 3}));
    expect(colors).toContain(a);
    expect(objectColor(detection({object_id: 'obj-12', track_id: 99}))).toBe(a);
  });
});

describe('cameraName', () => {
  it('names the known cameras and humanizes the rest', () => {
    expect(cameraName('lane')).toBe('Lane camera');
    expect(cameraName('overhead')).toBe('Overhead camera');
    expect(cameraName('scan')).toBe('Barcode scan camera');
    expect(cameraName('side_door')).toBe('side door');
  });
});
