CREATE PROCEDURE edge_full_cursor_block
AS
BEGIN
    DECLARE @id INT;
    DECLARE @name VARCHAR(100);

    DECLARE user_cursor CURSOR FOR
    SELECT id, name FROM users WHERE active = 1;

    OPEN user_cursor;

    FETCH NEXT FROM user_cursor INTO @id, @name;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        INSERT INTO audit_log(user_id, message)
        VALUES (@id, @name);

        FETCH NEXT FROM user_cursor INTO @id, @name;
    END

    CLOSE user_cursor;
    DEALLOCATE user_cursor;
END;
