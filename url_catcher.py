#!/usr/bin/python3

import bottle
import validators
import html
import os
import os.path
import time
import json
import smtplib
import email.mime.text
import tempfile
import shutil

slowdown_reset = 60 * 60 * 24
ips_dir = 'ips'
lists_dir = 'lists'
captchas_dir = 'captchas'
customizations_path = 'customizations.json'
messages = {
    'internalServerError': 'Internal server error.',
    'badPageName': 'Bad page name.',
    'wrongCaptcha': 'Wrong captcha.',
    'invalidURL': 'Invalid URL.',
    'recordedURL': 'Recorded URL: ',
    'pleaseWait': 'Too many attempts from your IP. Wait this many seconds: ',
    'mailSubject': '[url_catcher.py] New URL submitted',
    'mailBodyPage': 'New URL submitted for page: ',
    'mailBodyURL': 'URL is: ',
}
mail_config = {
    'from': 'foo@example.org',
    'to': 'bar@example.org',
}
if os.path.isfile(customizations_path):
    customizations_file = open(customizations_path)
    customizations = json.load(customizations_file)
    customizations_file.close()
    for key in customizations['translations']:
        messages[key] = customizations['translations'][key]
    for key in customizations['mailConfig']:
        mail_config[key] = customizations['mailConfig'][key]
    if 'slowdownReset' in customizations:
        slowdown_reset = customizations['slowdownReset']
os.makedirs(ips_dir, exist_ok=True)
os.makedirs(lists_dir, exist_ok=True)


def atomic_write(path, content, mode):
    """Atomic write/append to file."""
    _, tmpPath = tempfile.mkstemp()
    if 'a' == mode:
        shutil.copy2(path, tmpPath)
    f = open(tmpPath, mode)
    f.write(content)
    f.flush()
    os.fsync(f.fileno())
    f.close()
    os.rename(tmpPath, path)


def send_mail(page, url):
    """Send mail telling about page URL list update."""
    body = messages['mailBodyPage'] + page + '\n' + messages['mailBodyURL'] + \
        url
    msg = email.mime.text.MIMEText(body)
    msg['Subject'] = messages['mailSubject']
    msg['From'] = mail_config['from']
    msg['To'] = mail_config['to']
    s = smtplib.SMTP('localhost')
    s.send_message(msg)
    s.quit()


@bottle.error(500)
def internal_error(error):
    """If trouble, don't leak bottle.py's detailed error description."""
    return messages['internalServerError']


@bottle.post('/uwsgi/post_link')
def post_link():
    """Record URL if all sane, send mail to curator."""

    # Slow down repeat requests.
    now = int(time.time())
    start_date = now
    attempts = 0
    rewrite = True
    ip = bottle.request.environ.get('REMOTE_ADDR')
    ip_file_path = ips_dir + '/' + ip
    try:
        if os.path.isfile(ip_file_path):
            ip_file = open(ip_file_path, 'r')
            ip_data = ip_file.readlines()
            ip_file.close()
            old_start_date = int(ip_data[0])
            if old_start_date + slowdown_reset > now:
                attempts = int(ip_data[1])
                start_date = old_start_date
                wait_period = 2**attempts
                if start_date + wait_period > now:
                    limit = min(start_date + wait_period,
                        start_date + slowdown_reset)
                    rewrite = False
                    remaining_wait = limit - now
                    msg = messages['pleaseWait'] + str(remaining_wait)
                    return bottle.HTTPResponse(msg, 429,
                        {'Retry-After': str(remaining_wait)})
                attempts += 1 
    except:
        raise
    finally:
        if rewrite:
            atomic_write(ip_file_path,
                str(start_date) + '\n' + str(attempts), 'w')

    # Derive page / page file name.
    page = bottle.request.forms.get('page')
    if '\0' in page or '/' in page or '.' in page or len(page.encode()) > 255:
        return bottle.HTTPResponse(messages['badPageName'], 400)

    # Test captcha.
    captcha_file = open(captchas_dir + '/' + page, 'r')
    captcha_correct = captcha_file.readline().rstrip()
    captcha_file.close()
    captcha_input = bottle.request.forms.get('captcha')
    if captcha_correct != captcha_input:
        return bottle.HTTPResponse(messages['wrongCaptcha'], 400)

    # Record URL.
    url = bottle.request.forms.get('url')
    if not validators.url(url):
        return bottle.HTTPResponse(messages['invalidURL'], 400)
    send_mail(page, url)
    atomic_write(lists_dir + '/' + page, url + '\n', 'a')
    url_html = html.escape(url)

    # Response body.
    return messages['recordedURL'] + url_html


bottle.debug(True)
# Non-uWSGI mode.
if __name__ == '__main__':
    bottle.run(host='localhost', port=8080)
# uWSGI mode.
else:
    app = application = bottle.default_app()
