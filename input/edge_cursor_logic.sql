CREATE PROCEDURE edge_cursor_logic
AS
BEGIN
    DECLARE @id INT, @name TEXT;

    SELECT id, name FROM users WHERE active = 1;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        INSERT INTO audit_log(user_id, message) VALUES(@id, @name);
    END
END
