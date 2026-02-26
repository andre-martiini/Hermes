
/**
 * Converts a time string (HH:mm) to minutes from midnight.
 * @param time HH:mm string
 * @returns number of minutes
 */
export const timeToMinutes = (time: string): number => {
  if (!time) return 0;
  const [h, m] = time.split(':').map(Number);
  return h * 60 + m;
};

/**
 * Converts minutes from midnight to a time string (HH:mm).
 * @param minutes number of minutes
 * @returns HH:mm string
 */
export const minutesToTime = (minutes: number): string => {
  const h = Math.max(0, Math.min(23, Math.floor(minutes / 60)));
  const m = Math.max(0, Math.min(59, Math.floor(minutes % 60)));
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
};

/**
 * Snaps a value (minutes) to the nearest step (e.g., 15 minutes).
 * @param value value to snap
 * @param step step size
 * @returns snapped value
 */
export const snapToGrid = (value: number, step: number = 15): number => {
  return Math.round(value / step) * step;
};

/**
 * Calculates the Y pixel position from a time string.
 * @param timeStr HH:mm string
 * @param hourHeight pixels per hour
 * @returns Y position in pixels
 */
export const getYFromTime = (timeStr: string, hourHeight: number = 60): number => {
  const minutes = timeToMinutes(timeStr);
  return (minutes / 60) * hourHeight;
};

/**
 * Calculates the time string from a Y pixel position.
 * @param y Y position in pixels
 * @param hourHeight pixels per hour
 * @param step step in minutes (default 15)
 * @returns HH:mm string
 */
export const getTimeFromY = (y: number, hourHeight: number = 60, step: number = 15): string => {
  const minutes = (y / hourHeight) * 60;
  const snappedMinutes = snapToGrid(minutes, step);
  return minutesToTime(snappedMinutes);
};

/**
 * Calculates the column index from an X pixel position.
 * @param x X position in pixels relative to the grid container
 * @param totalWidth total width of the grid container
 * @param totalColumns number of columns (days)
 * @returns column index (0 to totalColumns - 1)
 */
export const getColumnFromX = (x: number, totalWidth: number, totalColumns: number): number => {
  if (totalColumns <= 0) return 0;
  const colWidth = totalWidth / totalColumns;
  const colIndex = Math.floor(x / colWidth);
  return Math.max(0, Math.min(totalColumns - 1, colIndex));
};
