import assert from 'node:assert/strict';

/** Claim through the actual UI, checking the authoritative receipt before closing. */
export async function openCoinBag(page) {
  const response = page.waitForResponse(r => r.url().endsWith('/rewards/claim/') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Mở túi coin · 20–60', exact: true }).click();
  const receipt = await (await response).json();
  assert.ok([20, 25, 30, 40, 60].includes(receipt.coin_amount));
  await page.getByText(`+${receipt.coin_amount} coin`, { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
  return receipt;
}
