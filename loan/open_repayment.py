from contextvars import ContextVar


_open_repayment_amount = ContextVar('open_repayment_amount', default=None)
_open_repayment_enabled = ContextVar('open_repayment_enabled', default=False)
_installed_modules = set()


def set_open_repayment(amount):
    _open_repayment_enabled.set(True)
    _open_repayment_amount.set(amount)


def clear_open_repayment():
    _open_repayment_enabled.set(False)
    _open_repayment_amount.set(None)


def open_repayment_enabled():
    return _open_repayment_enabled.get()


def get_open_repayment_amount():
    return _open_repayment_amount.get()


def install_open_repayment_handlers(module):
    module_id = id(module)
    if module_id in _installed_modules:
        return

    original_combination_check = module.combination_check
    original_repayment = module.repayment

    def combination_check_with_open_repayment(amount, num_fns):
        if open_repayment_enabled():
            return 0
        return original_combination_check(amount, num_fns)

    def repayment_with_open_repayment(amount, interest_type, fns):
        repayment_amount = get_open_repayment_amount()
        if open_repayment_enabled() and repayment_amount is not None:
            return float(repayment_amount)
        return original_repayment(amount, interest_type, fns)

    module.combination_check = combination_check_with_open_repayment
    module.repayment = repayment_with_open_repayment
    _installed_modules.add(module_id)
