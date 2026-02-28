export const resolveTwoStepAction = (pendingKey: string | null, clickedKey: string) => {
  if (pendingKey === clickedKey) {
    return { pendingKey: null as string | null, confirmed: true };
  }
  return { pendingKey: clickedKey, confirmed: false };
};
