CREATE PROCEDURE edge_case_nested_raises
AS
BEGIN
    DECLARE @i INT
    SET @i = 0

    IF @i = 0
    BEGIN
        WHILE @i < 3
        BEGIN
            SET @i = @i + 1

            IF @i = 2
            BEGIN
                PRINT 'Reached 2'

                IF @i = 3
                BEGIN
                    THROW
                END
            END
        END

        RAISERROR('End of loop', 16, 1)
    END

    RETURN 0
END
