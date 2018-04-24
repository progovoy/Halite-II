import logging
import traceback
import urllib.parse

import flask
from flask import redirect
import sqlalchemy
from flask_oauthlib.client import OAuth, OAuthException

from .. import app, config, model, util
from ..util import cross_origin


login_log = logging.getLogger("login")


oauth_login = flask.Blueprint("github_login", __name__)
oauth_logout = flask.Blueprint("oauth_logout", __name__)

oauth = OAuth(app)
github = oauth.remote_app(
    "github",
    consumer_key=config.OAUTH_GITHUB_CONSUMER_KEY,
    consumer_secret=config.OAUTH_GITHUB_CONSUMER_SECRET,
    request_token_params={"scope": "user:email"},
    base_url="https://api.github.com",
    request_token_url=None,
    access_token_method="POST",
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
)


@oauth_login.route("/github")
def github_login_init():
    url = urllib.parse.urlparse(config.API_URL)
    base_url = url.scheme + "://" + url.netloc
    full_url = urllib.parse.urljoin(
        base_url,
        flask.url_for(".github_login_callback"))

    return redirect(full_url)


@oauth_login.route("/me")
@cross_origin(methods=["GET"], origins=config.CORS_ORIGINS, supports_credentials=True)
def me():
    if "user_id" in flask.session:
        return flask.jsonify({
            "user_id": flask.session["user_id"],
        })
    else:
        return flask.jsonify(None)


@oauth_logout.route("/", methods=["POST"])
@cross_origin(methods=["POST"], origins=config.CORS_ORIGINS, supports_credentials=True)
def logout():
    flask.session.clear()
    return util.response_success()


@oauth_login.route("/response/github")
def github_login_callback():
    response = None

    if response is None:
        login_log.error('Great success(!)')

    flask.session["github_token"] = ('0xdeadbeef', "")

    user_data = {'login': 'yanir', 'id': 1}

    username = user_data["login"]
    github_user_id = user_data["id"]
    email = 'yanirj@final.co.il'

    with model.engine.connect() as conn:
        user = conn.execute(sqlalchemy.sql.select([
            model.users.c.id,
        ]).select_from(model.users).where(
            (model.users.c.oauth_provider == 1) &
            (model.users.c.oauth_id == github_user_id)
        )).first()

        if not user:
            # New user
            new_user_id = conn.execute(model.users.insert().values(
                username=username,
                github_email=email,
                oauth_id=github_user_id,
                oauth_provider=1,
            )).inserted_primary_key
            flask.session["user_id"] = new_user_id[0]
            return flask.redirect(urllib.parse.urljoin(config.SITE_URL, "/create-account"))
        else:
            flask.session["user_id"] = user["id"]
            return flask.redirect(urllib.parse.urljoin(config.SITE_URL, "/user/?me"))

    if "redirectURL" in flask.request.args:
        return flask.redirect(flask.request.args["redirectURL"])

    return util.response_success()

@github.tokengetter
def github_tokengetter():
    return flask.session.get("github_token")
