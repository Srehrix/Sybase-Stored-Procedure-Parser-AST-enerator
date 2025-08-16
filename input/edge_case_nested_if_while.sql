CREATE PROCEDURE edge_case_nested_if_while
AS
BEGIN
    DECLARE @i INT
    SET @i = 0

    WHILE @i < 3
    BEGIN
        SET @i = @i + 1

        IF @i = 2
        BEGIN
            EXEC log_event @i
            RETURN -1
        END
    END

    RETURN 0
END
