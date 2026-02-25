
import { timeToMinutes, minutesToTime, snapToGrid, getYFromTime, getTimeFromY, getColumnFromX } from './calendarUtils';
import assert from 'assert';

console.log('Running Calendar Utils Tests...');

// Test timeToMinutes
assert.strictEqual(timeToMinutes('00:00'), 0, '00:00 should be 0 minutes');
assert.strictEqual(timeToMinutes('01:30'), 90, '01:30 should be 90 minutes');
assert.strictEqual(timeToMinutes('23:59'), 1439, '23:59 should be 1439 minutes');

// Test minutesToTime
assert.strictEqual(minutesToTime(0), '00:00', '0 minutes should be 00:00');
assert.strictEqual(minutesToTime(90), '01:30', '90 minutes should be 01:30');
assert.strictEqual(minutesToTime(1439), '23:59', '1439 minutes should be 23:59');

// Test snapToGrid
assert.strictEqual(snapToGrid(14, 15), 15, '14 should snap to 15');
assert.strictEqual(snapToGrid(7, 15), 0, '7 should snap to 0'); // Rounding
assert.strictEqual(snapToGrid(8, 15), 15, '8 should snap to 15'); // Rounding

// Test getYFromTime
// 60px per hour means 1px per minute
assert.strictEqual(getYFromTime('01:00', 60), 60, '01:00 should be 60px');
assert.strictEqual(getYFromTime('00:30', 60), 30, '00:30 should be 30px');

// Test getTimeFromY
// 60px per hour, 15m step
assert.strictEqual(getTimeFromY(60, 60, 15), '01:00', '60px should be 01:00');
assert.strictEqual(getTimeFromY(30, 60, 15), '00:30', '30px should be 00:30');
assert.strictEqual(getTimeFromY(35, 60, 15), '00:30', '35px should snap to 00:30 (nearest 15m is 30m)'); // 35px = 35min. Snap(35, 15) -> 30.

// Test getColumnFromX
// width 700, 7 cols -> 100px per col
assert.strictEqual(getColumnFromX(50, 700, 7), 0, '50px should be col 0');
assert.strictEqual(getColumnFromX(150, 700, 7), 1, '150px should be col 1');
assert.strictEqual(getColumnFromX(650, 700, 7), 6, '650px should be col 6');
assert.strictEqual(getColumnFromX(800, 700, 7), 6, '800px (out of bounds) should be col 6'); // Max check

console.log('All tests passed!');
