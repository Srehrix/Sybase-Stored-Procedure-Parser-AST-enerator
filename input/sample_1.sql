CREATE PROCEDURE [dbo].[sp_check_employee]
    @emp_id INT,
    @emp_name VARCHAR(100)
AS
BEGIN
    DECLARE @emp_exists INT
    DECLARE @emp_message VARCHAR(200)

    SET @emp_exists = 0

    SELECT @emp_exists = COUNT(*) 
    FROM Employees 
    WHERE EmployeeID = @emp_id AND Name = @emp_name

    IF @emp_exists > 0
    BEGIN
        SET @emp_message = 'Employee found'
    END
    ELSE
    BEGIN
        SET @emp_message = 'Employee not found'
    END

    SELECT @emp_message AS Message

    RETURN
END
