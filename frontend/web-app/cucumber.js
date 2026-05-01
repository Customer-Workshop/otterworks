module.exports = {
  default: {
    requireModule: ["ts-node/register"],
    require: ["bdd/steps/**/*.ts", "bdd/support/**/*.ts"],
    paths: ["bdd/features/**/*.feature"],
    format: ["progress-bar"],
    publishQuiet: true,
    worldParameters: {},
  },
};
