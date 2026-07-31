from django import forms

class DatePickerInput(forms.DateInput):
    input_type = 'text'

    def format_value(self, value):
        # Render initial values in the system Date Settings format (falls back
        # to Django's default when no explicit format was requested).
        if self.format is None:
            from moromafinance.dateformats import format_system_date
            formatted = format_system_date(value)
            if formatted is not None:
                return formatted
        return super().format_value(value)

    def __init__(self, attrs=None, format=None):
        default_attrs = {'class': 'flatpickr-date', 'placeholder': 'Select date...'}
        if attrs:
            default_attrs.update(attrs)
            if 'class' in attrs:
                default_attrs['class'] = attrs['class'] + ' flatpickr-date'
        super().__init__(attrs=default_attrs, format=format)

class TimePickerInput(forms.TimeInput):
    input_type = 'text'

    def __init__(self, attrs=None, format=None):
        default_attrs = {'class': 'flatpickr-time', 'placeholder': 'Select time...'}
        if attrs:
            default_attrs.update(attrs)
            if 'class' in attrs:
                default_attrs['class'] = attrs['class'] + ' flatpickr-time'
        super().__init__(attrs=default_attrs, format=format)

class DateTimePickerInput(forms.DateTimeInput):
    input_type = 'text'

    def __init__(self, attrs=None, format=None):
        default_attrs = {'class': 'flatpickr-datetime', 'placeholder': 'Select date & time...'}
        if attrs:
            default_attrs.update(attrs)
            if 'class' in attrs:
                default_attrs['class'] = attrs['class'] + ' flatpickr-datetime'
        super().__init__(attrs=default_attrs, format=format)
