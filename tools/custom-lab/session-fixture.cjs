const { execFileSync } = require('node:child_process');
const path = require('node:path');
const python = path.resolve('.venv/Scripts/python.exe');
const run = (code, input = '') => execFileSync(python, ['backend/manage.py', 'shell', '-c', code], { input, encoding: 'utf8' }).trim().split(/\r?\n/).at(-1);
exports.create = () => JSON.parse(run("import json,secrets; from users.models import User; from rest_framework_simplejwt.tokens import AccessToken; suffix=secrets.token_hex(6); password=secrets.token_urlsafe(24); admin=User.objects.create_user(username='qa-session-'+suffix,email='qa-session-'+suffix+'@example.invalid',password=password,role=User.Role.ADMIN); customer=User.objects.create_user(username='qa-customer-'+suffix,email='qa-customer-'+suffix+'@example.invalid',password=password); print(json.dumps({'admin':admin.username,'customer':customer.username,'password':password,'customerAccess':str(AccessToken.for_user(customer))}))"));
exports.remove = fixture => run("import json,sys; from users.models import User; from cart.models import CartItem; data=json.load(sys.stdin); assert data['admin'].startswith('qa-session-') and data['customer'].startswith('qa-customer-'); users=User.objects.filter(username__in=[data['admin'],data['customer']],email__endswith='@example.invalid'); CartItem.objects.filter(cart__user__in=users).delete(); users.delete(); print('clean')", JSON.stringify({ admin: fixture.admin, customer: fixture.customer }));
exports.login = async (page, fixture, base = 'http://127.0.0.1:8765') => {
  await page.goto(`${base}/backoffice/login/`);
  await page.locator('#id_username').fill(fixture.admin);
  await page.locator('#id_password').fill(fixture.password);
  await Promise.all([page.waitForURL(`${base}/backoffice/`), page.locator('button[type="submit"]').click()]);
};
