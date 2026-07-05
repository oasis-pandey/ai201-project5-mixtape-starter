# Mixtape Bug Hunt Submission

## Part 1: Codebase Map

### Main Files and Their Roles
The Mixtape app is a Flask application using SQLAlchemy for the database, structured into routes (controllers) and services (business logic).

* **`app.py`**: The Flask application factory. It handles the database setup (`db.init_app(app)`), configures the application environment, and registers all the route blueprints (like `/songs`, `/feed`, etc.).
* **`models.py`**: Defines the SQLAlchemy ORM schema for the application's database. It includes classes for `User`, `Song`, `ListeningEvent`, `Rating`, `Playlist`, and `Notification`, as well as association tables for many-to-many relationships (e.g., `friendships`, `song_tags`, `playlist_entries`).
* **`routes/`**: Contains the routing logic (Blueprints) for the application's API endpoints. These files define the HTTP methods (GET, POST) and URLs, and map them to handler functions. These handlers parse incoming requests and delegate the heavy lifting to the `services/` layer. 
* **`services/`**: The core business logic layer. Files here (like `feed_service.py` or `streak_service.py`) interact directly with the database via `models.py` to fetch, create, or update data, and return structured results back to the routes.
* **`seed_data.py`**: A utility script used to populate the database with initial test data (users, songs, events) so the app can be tested locally.
* **`tests/`**: Contains the test suite using `pytest`. It includes tests for the various service layer logic (e.g., `test_streaks.py`, `test_search.py`).

### Data Flow Example: Friends Listening Now Feed
When a user wants to see what their friends have been listening to recently, the following data flow occurs:

1. **Client Request**: The client sends an HTTP GET request to `GET /feed/<user_id>/listening-now`.
2. **Route Handler (`routes/feed.py`)**: The `listening_now` function catches the request and extracts the `user_id` from the URL. It then calls the business logic function `get_friends_listening_now(user_id)`.
3. **Service Logic (`services/feed_service.py`)**: 
   - The service fetches the current `User` from the database.
   - It retrieves the list of the user's friends and determines a time cutoff (the last 24 hours).
   - It queries the `ListeningEvent` table for any events involving those friends since the cutoff time, sorted by the most recent.
   - It deduplicates the results to ensure only the most recent song for each friend is returned, and formats the data into a list of dictionaries containing friend and song details.
4. **Response**: The `listening_now` route handler receives this list, packages it into a JSON response with a count (`{"feed": feed, "count": len(feed)}`), and returns it to the client.

## Part 2: Bug Fixes

### Issue #1: My listening streak keeps resetting

**How you reproduced it:**
I reproduced this by considering the logic around when streaks reset. If a user has a streak and then listens to a song exactly one day later (on a Sunday), the app incorrectly resets their streak to 1 instead of incrementing it, because the streak logic treated Sundays as a week-boundary condition to reset.

**How you found the root cause:**
I traced the feature from the bug description to `services/streak_service.py` where the `update_listening_streak` function resides. By reading the `days_since_last == 1` condition, I noticed an additional check for `today.weekday() != 6` which directly affects what happens on Sundays (since `datetime.weekday()` returns 6 for Sunday). 

**The root cause:**
The function `update_listening_streak` checks if the user listened exactly one day ago. However, the condition `elif days_since_last == 1 and today.weekday() != 6:` explicitly prevents the streak from incrementing if the current day is Sunday. Instead, it falls through to the `else` block which resets the streak to 1. There is no requirement for streaks to reset on Sundays.

**Your fix and side-effect check:**
I removed the `and today.weekday() != 6` check so that the condition is simply `elif days_since_last == 1:`. This allows the streak to correctly increment on Sundays. As a side-effect check, I confirmed that streaks still reset appropriately when `days_since_last > 1` (i.e. when a day is skipped) since the `else` block remains intact.

---

### Issue #3: The same song keeps showing up twice in search

**How you reproduced it:**
I reviewed the `search_songs` function to understand how it queries the database. If a song in the database has multiple tags associated with it (e.g. via the `song_tags` association table), searching for its title or artist will return multiple identical rows for that song.

**How you found the root cause:**
Looking at `services/search_service.py`, I examined the SQLAlchemy query used to fetch songs. I noticed a `.outerjoin(song_tags, Song.id == song_tags.c.song_id)` being applied, but no `.distinct()` was used, nor was there any filtering done on the tags table itself.

**The root cause:**
The explicit outer join with `song_tags` creates a cartesian product, generating a row for every tag a song has. Since the query ends with `.all()`, SQLAlchemy creates multiple duplicate `Song` instances for songs with multiple tags, which are then passed back in the search results.

**Your fix and side-effect check:**
I removed the `.outerjoin()` call entirely from the query. As a side-effect check, I verified in `models.py` that the `Song.tags` relationship uses `lazy="subquery"`. This means SQLAlchemy will automatically and correctly fetch the associated tags for each song without needing a manual join in the search query, ensuring the tags are still present in the returned JSON.

---

### Issue #5: The last song in a playlist never shows up

**How you reproduced it:**
By looking at how playlist songs are retrieved, if a playlist has N songs, it consistently returns N - 1 songs. The final song in the playlist's order is consistently missing from the response.

**How you found the root cause:**
I navigated to `services/playlist_service.py` to examine the `get_playlist_songs` function which handles the retrieval of songs for a given playlist. At the very end of the function, I noticed a Python list slice being applied to the returned results.

**The root cause:**
The function returns `[song.to_dict() for song in songs[:-1]]`. The `[:-1]` slice explicitly excludes the last element of the list, which drops the final song of the playlist from the returned JSON.

**Your fix and side-effect check:**
I changed the return statement to `[song.to_dict() for song in songs]`, removing the slicing logic entirely. For my side-effect check, I made sure that the query ordering `order_by(asc(playlist_entries.c.position))` was untouched, ensuring the full list of songs is now returned in the correct sequential order.

---

### Issue #2: Friends Listening Now shows people from yesterday

**How you reproduced it:**
I investigated the feed functionality by considering how events are filtered by time. If the app uses a large time window (like 24 hours), it will show users who listened to songs the previous day under a feature named "Friends Listening Now".

**How you found the root cause:**
I inspected `services/feed_service.py` to see how `get_friends_listening_now` filters events. I found that it subtracts `RECENT_THRESHOLD` from the current time to create a `cutoff` date. The `RECENT_THRESHOLD` was explicitly defined at the top of the file as `timedelta(hours=24)`.

**The root cause:**
The root cause was a configuration error in the threshold duration. By setting the threshold to 24 hours, the "Listening Now" feature was functioning more like a "Listened Recently" feature, returning events from the entire previous calendar day rather than current or immediately recent activity.

**Your fix and side-effect check:**
I changed the `RECENT_THRESHOLD` to `timedelta(hours=1)` to better reflect the "Now" semantics. As a side-effect check, I verified that `get_activity_feed` in the same file was unaffected, since it correctly relies on a `limit` of events rather than a time-based cutoff.

---

### Issue #4: I got notified when a friend added my song to a playlist but not when they rated it

**How you reproduced it:**
I analyzed the logic for song interactions. If a user adds a song to a playlist, a notification is generated for the original sharer. However, if the user rates that same song, no notification is ever created.

**How you found the root cause:**
I opened `services/notification_service.py` and compared `add_to_playlist` with `rate_song`. The `add_to_playlist` function explicitly calls `create_notification` for the original sharer. The `rate_song` function updates or inserts a `Rating` record, but completely omits the call to `create_notification`.

**The root cause:**
The root cause was simply missing logic. The architectural pattern for notifications (manually calling `create_notification` when a relevant action occurs) was not applied to the `rate_song` function, meaning the system silently stored the rating without informing the original sharer.

**Your fix and side-effect check:**
I added the missing logic to `rate_song` right before `db.session.commit()`. It checks if `song.shared_by != user_id` and, if so, creates a `song_rated` notification. As a side-effect check, I ran my new regression test (`tests/test_notifications.py`) to confirm the notification is correctly persisted without breaking the rating storage. I also ensured a user doesn't get notified for rating their own song.

---

### Stretch Feature: Regression Test

I added a regression test for Bug #4 in `tests/test_notifications.py` (`test_rate_song_creates_notification`). It simulates a user rating a song shared by another user and asserts that exactly one `song_rated` notification is created with the correct recipient and message body.

---

### AI Usage
During this project, I used an AI assistant to help navigate the codebase, understand the project requirements, and trace the code execution for each bug. The AI helped me locate the buggy files based on the bug descriptions. I verified the AI's findings by reading the actual code logic (like the `[:-1]` slice and the `weekday() != 6` check) before applying the targeted fixes and creating the commits.
