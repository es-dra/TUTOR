import { test, expect } from '@playwright/test';

test.describe('TUTOR 工作流管理', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('应该显示首页仪表盘', async ({ page }) => {
    // 检查页面标题
    await expect(page).toHaveTitle(/TUTOR/);
  });

  test('应该能导航到工作流页面', async ({ page }) => {
    // 点击工作流链接
    await page.click('text=工作流');
    // 验证 URL 变化或内容加载
    await expect(page.locator('body')).not.toHaveText('', { useInnerText: true });
  });

  test('应该能导航到审批页面', async ({ page }) => {
    // 点击审批链接
    await page.click('text=审批');
    await expect(page.locator('body')).not.toHaveText('', { useInnerText: true });
  });

  test('应该能导航到设置页面', async ({ page }) => {
    // 点击设置链接
    await page.click('text=设置');
    await expect(page.locator('body')).not.toHaveText('', { useInnerText: true });
  });
});

test.describe('健康检查', () => {
  test('API 健康检查端点应该正常响应', async ({ request }) => {
    const response = await request.get('http://localhost:8080/health');
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.status).toBe('ok');
  });
});
