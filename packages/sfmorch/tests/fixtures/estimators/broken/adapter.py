from sfmkit import Ctx, module


@module
def run(ctx: Ctx):
    raise RuntimeError("staged estimator failure: out of memory")
