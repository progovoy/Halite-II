"""
User API endpoints - create/update/delete/list users and user data
"""

import uuid

import flask
import sqlalchemy
import tld

from .. import config, model, notify, util

from . import util as web_util
from .blueprint import web_api


tld.update_tld_names()


def make_user_record(row, *, logged_in, total_users=None):
    """Given a database result row, create the JSON user object."""
    user = {
        "user_id": row["user_id"],
        "username": row["username"],
        "level": row["player_level"],
        "organization_id": row["organization_id"],
        "organization": row["organization_name"],
        "country_code": row["country_code"],
        "country_subdivision_code": row["country_subdivision_code"],
        "num_bots": row["num_bots"],
        "num_submissions": int(row["num_submissions"]),
        "num_games": int(row["num_games"]),
        "score": float(row["score"]),
        "mu": float(row["mu"]),
        "sigma": float(row["sigma"]),
        "rank": int(row["rank"]) if row["rank"] is not None else None,
        "is_email_good":row["is_email_good"],
        "is_gpu_enabled": row["is_gpu_enabled"]
    }

    if total_users and row["rank"] is not None:
        user["tier"] = util.tier(row["rank"], total_users)
    else:
        user["tier"] = None

    if "personal_email" in row and row["personal_email"] is None and logged_in:
        # User is new user, indicate this when they are logged in
        user["is_new_user"] = True

    return user


def verify_affiliation(org_id, email_to_verify, provided_code):
    """
    Verify whether a user is allowed to associate with an organization.

    :param org_id: The ID of the organization in question.
    :param email_to_verify: The email of the user.
    :param provided_code: A verification code for the org, if provided.
    :return: Nothing (raises util.APIError if user cannot affiliate)
    """
    email_error = util.APIError(400, message="Invalid email for organization.")
    verification_error = util.APIError(400, message="Invalid verification code.")

    with model.engine.connect() as conn:
        org = conn.execute(model.organizations.select().where(
            model.organizations.c.id == org_id
        )).first()

        if org is None:
            raise util.APIError(404, message="This organization does not exist.")

        if org["kind"] == "High School":
            # Don't require validation for high schools - we manually check
            return

        if not email_to_verify:
            raise email_error

        # Verify the email against the org
        if "@" not in email_to_verify:
            raise util.APIError(400, message="Email invalid.")
        domain = email_to_verify.split("@")[1].strip().lower()
        domain_filter = model.organization_email_domains.c.domain == domain
        # Also use the TLD to search
        domain_tld = tld.get_tld(domain, fail_silently=True, fix_protocol=True)
        if domain_tld:
            domain_filter |= model.organization_email_domains.c.domain == domain_tld
        count = conn.execute(sqlalchemy.sql.select([
            sqlalchemy.sql.func.count()
        ]).select_from(model.organization_email_domains).where(
            (model.organization_email_domains.c.organization_id == org_id) &
            domain_filter
        )).first()[0]

        can_verify_by_code = org["verification_code"] is not None
        code_correct = org["verification_code"] == provided_code

        if count == 0:
            if can_verify_by_code and not code_correct:
                raise verification_error
            else:
                raise email_error

    # Otherwise, no verification method defined, or passed verification


def send_verification_email(recipient, verification_code):
    """
    Send the verification email to the user.

    :param notify.Recipient recipient:
    :param verification_code:
    :return:
    """

    notify.send_templated_notification(
        recipient,
        config.VERIFY_EMAIL_TEMPLATE,
        {
            "verification_url": util.build_site_url("/verify-email", {
                "verification_code": verification_code,
                "user_id": recipient.user_id,
            }),
        },
        config.GOODNEWS_ACCOMPLISHMENTS,
        config.C_EMAIL_VERIFICATION
    )


def send_confirmation_email(recipient):
    """
    Send a confirmation email to the user (let them know that they registered)

    :param notify.Recipient recipient:
    """

    return


def guess_affiliation(email):
    with model.engine.connect() as conn:
        if "@" not in email:
            return None, None
        domain = email.split("@")[1].strip().lower()
        domain_filter = model.organization_email_domains.c.domain == domain
        # Also use the TLD to search
        domain_tld = tld.get_tld(domain, fail_silently=True, fix_protocol=True)
        if domain_tld:
            domain_filter |= model.organization_email_domains.c.domain == domain_tld

        organization = conn.execute(sqlalchemy.sql.select([
            model.organizations.c.id,
            model.organizations.c.organization_name,
        ]).select_from(model.organizations).where(
            sqlalchemy.sql.exists(
                model.organization_email_domains.select().where(
                    (model.organization_email_domains.c.organization_id == model.organizations.c.id) &
                    domain_filter
                )
            )
        )).first()

        if organization:
            return organization["id"], organization["organization_name"]

        return None, None


@web_api.route("/user")
@util.cross_origin(methods=["GET", "POST"])
def list_users():
    result = []
    offset, limit = web_util.get_offset_limit()

    where_clause, order_clause, _ = web_util.get_sort_filter({
        "user_id": model.all_users.c.user_id,
        "username": model.all_users.c.username,
        "level": model.all_users.c.player_level,
        "organization_id": model.all_users.c.organization_id,
        "num_bots": model.all_users.c.num_bots,
        "num_submissions": model.all_users.c.num_submissions,
        "num_games": model.all_users.c.num_games,
        "rank": model.all_users.c.rank,
    })

    with model.engine.connect() as conn:
        total_users = conn.execute(model.total_ranked_users).first()[0]

        query = conn.execute(
            model.all_users.select()
                    .where(where_clause).order_by(*order_clause)
                    .offset(offset).limit(limit).reduce_columns())

        for row in query.fetchall():
            result.append(make_user_record(row, logged_in=False,
                                           total_users=total_users))

    return flask.jsonify(result)


@web_api.route("/user", methods=["POST"])
@util.cross_origin(methods=["GET", "POST"])
@web_util.requires_login(accept_key=False)
def create_user(*, user_id):
    """
    Set up a user created from an OAuth authorization flow.

    This endpoint, given an organization ID, generates a validation email
    and sets up the user's actual email.
    """
    body = flask.request.get_json()
    if not body:
        raise util.APIError(400, message="Please provide user data.")

    # Check if the user has already validated
    with model.engine.connect() as conn:
        user_data = conn.execute(model.users.select().where(
            model.users.c.id == user_id
        )).first()

        if user_data["verification_code"]:
            raise util.APIError(400, message="User needs to verify email.")

        if user_data["is_email_good"] == 1:
            raise util.APIError(400, message="You have already successfully confirmed your membership with this organization.")

    org_id = body.get("organization_id")
    email = body.get("email")
    level = body.get("level", user_data["player_level"])
    provided_code = body.get("verification_code", None)
    verification_code = uuid.uuid4().hex
    message = []

    # Values to insert into the database
    values = {
        "player_level": level,
    }

    # Perform validation on given values
    if "level" in body and not web_util.validate_user_level(body["level"]):
        raise util.APIError(400, message="Invalid user level.")

    if email is not None and "@" not in email:
        raise util.APIError(400, message="Invalid user email.")

    if "country_code" in body or "country_subdivision_code" in body:
        country_code = body.get("country_code")
        subdivision_code = body.get("country_subdivision_code")

        if subdivision_code and not country_code:
            raise util.APIError(
                400,
                message="Must provide country code if country subdivision code is given.")

        if not web_util.validate_country(country_code, subdivision_code):
            raise util.APIError(
                400, message="Invalid country/country subdivision code.")

        values["country_code"] = country_code
        values["country_subdivision_code"] = subdivision_code

    if org_id is None and email:
        # Guess an affiliation
        org_id, org_name = guess_affiliation(email)
        if org_id:
            message.append("You've been added to the {} organization.".format(org_name))
        else:
            message.append("We could not recognize this organization. Reach out to us at halite@halite.io for help.")

    # Figure out the situation with their email/organization
    if org_id is None and email is None:
        # Just use their Github email.
        values.update({
            "email": model.users.c.github_email,
            "is_email_good": 1,
            "organization_id": None,
            "player_level": level,
        })
    elif org_id is None:
        values.update({
            "email": email,
            "is_email_good": 0,
            "verification_code": verification_code,
            "organization_id": None,
            "player_level": level,
        })
    else:
        # Check the org
        verify_affiliation(org_id, email or user_data["github_email"],
                           provided_code)

    # Set the email verification code (if necessary).
    organization_name = None
    organization_is_high_school = False
    if email:
        values.update({
            "email": email,
            "is_email_good": 0,
            "verification_code": verification_code,
            "organization_id": org_id,
            "player_level": level,
        })

        if org_id:
            with model.engine.connect() as conn:
                organization_data = conn.execute(model.organizations.select(
                    model.organizations.c.id == org_id
                )).first()
                if organization_data:
                    organization_name = organization_data["organization_name"]
                    organization_is_high_school = organization_data["kind"] == "High School"

            if organization_is_high_school and level == "High School":
                values.update({
                    "is_email_good": 1,
                })
            else:
                send_verification_email(
                    notify.Recipient(user_id, user_data["username"], email,
                                     organization_name, level,
                                     user_data["creation_time"]),
                    verification_code)
        else:
            # Do not send verification email if we don't recognize it
            # as part of an organization
            values.update({
                "is_email_good": 1,
                "verification_code": None,
            })

        message.append("Please check your email for a verification code.")
    else:
        values.update({
            "email": model.users.c.github_email,
            "is_email_good": 1,
            "organization_id": org_id,
        })
        if org_id:
            message.append("You've been added to the organization!")

    with model.engine.connect() as conn:
        conn.execute(model.users.update().where(
            model.users.c.id == user_id
        ).values(**values))

    send_confirmation_email(
        notify.Recipient(user_id, user_data["username"], user_data["github_email"],
                         organization_name, level,
                         user_data["creation_time"]))

    return util.response_success({
        "message": "\n".join(message),
    }, status_code=201)


@web_api.route("/user/<int:intended_user>", methods=["GET"])
@util.cross_origin(methods=["GET", "PUT"])
@web_util.requires_login(optional=True, accept_key=True)
def get_user(intended_user, *, user_id):
    with model.engine.connect() as conn:
        query = model.all_users.select(
            model.all_users.c.user_id == intended_user)

        row = conn.execute(query).first()
        if not row:
            raise util.APIError(404, message="No user found.")

        total_users = conn.execute(model.total_ranked_users).first()[0]

        logged_in = user_id is not None and intended_user == user_id
        user = make_user_record(row, logged_in=logged_in,
                                total_users=total_users)

        return flask.jsonify(user)

# An endpoint for season 1 details, in the future at season 3 we need to make this more generic.
@web_api.route("/user/<int:intended_user>/season1", methods=["GET"])
@util.cross_origin(methods=["GET"])
@web_util.requires_login(optional=True, accept_key=True)
def get_user_season1(intended_user, *, user_id):
    with model.engine.connect() as conn:
        query = model.all_users.select(
            model.all_users.c.user_id == intended_user)

        row = conn.execute(query).first()
        if not row:
            raise util.APIError(404, message="No user found.")

        season_1_query = model.halite_1_users.select(
            model.halite_1_users.c.username == row["username"])

        season_1_row = conn.execute(season_1_query).first()

        if not season_1_row:
            raise util.APIError(404, message="No user found for Halite Season 1.")

        season_1_user = {
            "userID": season_1_row["userID"],
            "username": season_1_row["username"],
            "level": season_1_row["level"],
            "organization": season_1_row["organization"],
            "language": season_1_row["language"],
            "mu": season_1_row["mu"],
            "sigma": season_1_row["sigma"],
            "num_submissions": int(season_1_row["numSubmissions"]),
            "num_games": int(season_1_row["numGames"]),
            "rank": int(season_1_row["rank"]) if season_1_row["rank"] is not None else None,}

        return flask.jsonify(season_1_user)


@web_api.route("/user/<int:user_id>/verify", methods=["POST"])
@util.cross_origin(methods=["POST"])
def verify_user_email(user_id):
    verification_code = flask.request.form.get("verification_code")
    if not verification_code:
        raise util.APIError(400, message="Please provide verification code.")

    with model.engine.connect() as conn:
        query = sqlalchemy.sql.select([
            model.users.c.verification_code,
            model.users.c.is_email_good,
        ]).where(model.users.c.id == user_id)

        row = conn.execute(query).first()
        if not row:
            raise util.APIError(404, message="No user found.")

        if row["verification_code"] == verification_code:
            conn.execute(model.users.update().where(
                model.users.c.id == user_id
            ).values(
                is_email_good=1,
                verification_code="",
            ))
            return util.response_success({
                "message": "Email verified."
            })
        elif row["is_email_good"]:
            return util.response_success({
                "message": "Email already verified.",
            })

        raise util.APIError(400, message="Invalid verification code.")


@web_api.route("/user/<int:user_id>/verify/resend", methods=["POST"])
@util.cross_origin(methods=["POST"])
@web_util.requires_login()
def resend_user_verification_email(user_id):
    with model.engine.connect() as conn:
        row = conn.execute(
            model.users.select(model.users.c.id == user_id)
        ).first()

        if not row:
            raise util.APIError(404, message="No user found.")

        if row["is_email_good"]:
            return util.response_success({
                "message": "Email already verified.",
            })

        if not row["verification_code"]:
            raise util.APIError(
                400,
                message="Please finish setting up your account first.")

        send_verification_email(
            notify.Recipient(user_id, row["username"], row["email"],
                             None, row["player_level"],
                             row["creation_time"]),
            row["verification_code"])

        return util.response_success({
            "message": "Verification code resent.",
        })


@web_api.route("/user/<int:intended_user_id>", methods=["PUT"])
@util.cross_origin(methods=["GET", "PUT"])
@web_util.requires_login(accept_key=False)
def update_user(intended_user_id, *, user_id):
    if user_id != intended_user_id:
        raise web_util.user_mismatch_error()

    fields = flask.request.get_json()
    columns = {
        "level": "player_level",
        "country_code": "country_code",
        "country_subdivision_code": "country_subdivision_code",
        "organization_id": "organization_id",
        "email": "email",
        "verification_code": "organization_verification_code",
        "is_gpu_enabled": "is_gpu_enabled",
    }

    update = {}
    message = []

    for key in fields:
        if key not in columns:
            raise util.APIError(400, message="Cannot update '{}'".format(key))

        if (fields[key] is not None or
            key in ("country_code", "country_subdivision_code")):
            # Don't overwrite values with None/null (unless country code)
            update[columns[key]] = fields[key]

    # Validate new player level
    if (update.get("player_level") and
            not web_util.validate_user_level(update["player_level"])):
        raise util.APIError(400, message="Invalid player level.")

    with model.engine.connect() as conn:
        old_user = conn.execute(
            model.users.select(model.users.c.id == user_id)).first()
        if update.get("organization_id") is not None:
            org_data = conn.execute(
                model.organizations.select(model.organizations.c.id == update["organization_id"])
            ).first()
        else:
            org_data = None

    # Validate new country/region, if provided
    if update.get("country_code") or update.get("country_subdivision_code"):
        country_code = update.get("country_code", old_user["country_code"])
        # Only fill in old country subdivision code as default if user
        # didn't provide a new country code
        subdivision_code = update.get("country_subdivision_code",
                                      old_user["country_subdivision_code"]
                                      if not update.get("country_code")
                                      else None)

        if not web_util.validate_country(country_code, subdivision_code):
            raise util.APIError(
                400, message="Invalid country/country subdivision code.")

    if update.get("organization_id") is not None:
        # Associate the user with the organization
        current_level = update.get("player_level", old_user["player_level"])

        # Only require email for non-high-school
        if ("email" not in update and
            current_level != "High School" and
            org_data and org_data["kind"] == "High School"):
            raise util.APIError(
                400, message="Provide email to associate with organization."
            )
        verify_affiliation(update["organization_id"], update.get("email"),
                           update.get("organization_verification_code"))

    if update.get("organization_verification_code"):
        del update["organization_verification_code"]

    if update.get("email"):
        update["verification_code"] = uuid.uuid4().hex
        update["is_email_good"] = False

        if update.get("organization_id") is None:
            # Try and guess an affiliation
            org_id, org_name = guess_affiliation(update["email"])
            if org_id:
                message.append("You've been added to the {} organization.".format(org_name))
                update["organization_id"] = org_id
            else:
                update["organization_id"] = None
                message.append("We are setting up the association with the organization."
                               " Please verify your email, and we will contact you for more information if needed.")

        message.append("Please check your inbox for your verification email.")

    with model.engine.connect() as conn:
        conn.execute(model.users.update().where(
            model.users.c.id == user_id
        ).values(**update))

        user_data = conn.execute(sqlalchemy.sql.select(["*"]).select_from(
            model.users.join(
                model.organizations,
                model.users.c.organization_id == model.organizations.c.id,
                isouter=True
            )
        ).where(
            model.users.c.id == intended_user_id
        )).first()

        if "email" in update and update.get("organization_id"):
            send_verification_email(
                notify.Recipient(user_id, user_data["username"],
                                 user_data["email"],
                                 user_data["organization_name"],
                                 user_data["player_level"],
                                 user_data["creation_time"]),
                update["verification_code"])
        elif "email" in update:
            send_verification_email(
                notify.Recipient(user_id, user_data["username"],
                                 user_data["email"],
                                 "unknown",
                                 user_data["player_level"],
                                 user_data["creation_time"]),
                update["verification_code"])

    if message:
        return util.response_success({
            "message": "\n".join(message),
        })
    return util.response_success()


@web_api.route("/user/<int:intended_user_id>", methods=["DELETE"])
@web_util.requires_login(accept_key=True, admin=True)
def delete_user(intended_user_id, *, user_id):
    with model.engine.connect() as conn:
        conn.execute(model.games.delete().where(
            sqlalchemy.sql.exists(
                model.game_participants.select().where(
                    (model.game_participants.c.user_id == intended_user_id) &
                    (model.game_participants.c.game_id == model.games.c.id)
                )
            )
        ))
        conn.execute(model.users.delete().where(
            model.users.c.id == intended_user_id))
    return util.response_success()

@web_api.route("/user/addsubscriber/<string:recipient>", methods=["POST"])
@util.cross_origin(methods=["POST"])
def add_subscriber(recipient):
    notify.add_user_to_contact_list(recipient)
    notify.send_templated_notification_simple(
        recipient,
        config.NEW_SUBSCRIBER_TEMPLATE,
        config.GOODNEWS_ACCOMPLISHMENTS,
        config.C_NEWSLETTER_SUBSCRIPTION)
    return util.response_success()

@web_api.route("/invitation/user/<string:recipient>", methods=["POST"])
@util.cross_origin(methods=["POST"])
def invite_friend(recipient):
    notify.send_templated_notification_simple(
        recipient,
        config.INVITE_FRIEND_TEMPLATE,
        config.GOODNEWS_ACCOMPLISHMENTS,
        config.C_INVITE_FRIEND)
    return util.response_success()

@web_api.route("/api_key", methods=["POST"])
@web_api.route("/user/<int:intended_user>/api_key", methods=["POST"])
@util.cross_origin(methods=["POST"])
@web_util.requires_login(accept_key=False, association=True)
def reset_api_key(intended_user=None, *, user_id):
    if user_id != intended_user and intended_user is not None:
        raise web_util.user_mismatch_error(
            message="Cannot reset another user's API key.")

    with model.engine.connect() as conn:
        api_key = uuid.uuid4().hex

        conn.execute(model.users.update().where(
            model.users.c.id == user_id
        ).values(
            api_key_hash=config.api_key_context.hash(api_key),
        ))

        return util.response_success({
            "api_key": "{}:{}".format(user_id, api_key),
        }, status_code=201)

@web_api.route("/user/<int:intended_user_id>/history", methods=["GET"])
@util.cross_origin(methods=["GET"])
def get_rank_history(intended_user_id):
    result = []
    with model.engine.connect() as conn:
        history = conn.execute(sqlalchemy.sql.select([
                model.bot_history.c.version_number,
                model.bot_history.c.last_rank,
                model.bot_history.c.last_score,
                model.bot_history.c.last_num_players,
                model.bot_history.c.last_games_played,
                model.bot_history.c.when_retired
            ]).select_from(model.bot_history).where(model.bot_history.c.user_id == intended_user_id))

        for row in history.fetchall():
            history_item = {
                "bot_version": int(row["version_number"]),
                "last_rank": int(row["last_rank"]),
                "last_score": float(row["last_score"]),
                "last_num_players": int(row["last_num_players"]),
                "last_games_played": int(row["last_games_played"]),
                "when_retired": row["when_retired"],
            }

            result.append(history_item)

    return flask.jsonify(result)
