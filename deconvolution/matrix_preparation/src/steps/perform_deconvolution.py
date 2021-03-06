"""
File:         perform_deconvolution.py
Created:      2020/04/08
Last Changed: 2020/06/18
Author:       M.Vochteloo

Copyright (C) 2020 M.Vochteloo
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

A copy of the GNU General Public License can be found in the LICENSE file in the
root directory of this source tree. If not, see <https://www.gnu.org/licenses/>.
"""

# Standard imports.
import os

# Third party imports.
import numpy as np
import pandas as pd
from scipy.optimize import nnls

# Local application imports.
from general.utilities import prepare_output_dir, check_file_exists
from general.df_utilities import load_dataframe, save_dataframe


class PerformDeconvolution:
    def __init__(self, settings, profile_file, profile_df, ct_expr_file,
                 ct_expr_df, force, outdir):
        """
        The initializer for the class.


        :param settings: string, the settings.
        :param profile_file: string, the datafile contaioning the celltype
                             profile.
        :param profile_df: DataFrame, the celltype profile.
        :param ct_expr_file: string, the datafile containing expression
                             of the celltype profiles.
        :param ct_expr_df: string, the celltype expression.
        :param force: boolean, whether or not to force the step to redo.
        :param outdir: string, the output directory.
        """
        self.profile_file = profile_file
        self.profile_df = profile_df
        self.ct_expr_file = ct_expr_file
        self.ct_expr_df = ct_expr_df
        self.force = force

        # Prepare an output directories.
        self.outdir = os.path.join(outdir, 'perform_deconvolution')
        prepare_output_dir(self.outdir)

        # Construct the output paths.
        self.outpath = os.path.join(self.outdir, "deconvolution_table.txt.gz")

        # Create empty variable.
        self.deconvolution = None

    def start(self):
        print("Starting deconvolution.")
        self.print_arguments()

        # Check if output file exist.
        if check_file_exists(self.outpath) and not self.force:
            print("Skipping step, loading result.")
            self.deconvolution = load_dataframe(inpath=self.outpath,
                                                header=0, index_col=0)
        else:
            self.deconvolution = self.perform_deconvolution()
            self.save()

    def perform_deconvolution(self):
        if self.profile_df is None:
            # Load the celltype profile file.
            print("Loading cell type profile matrix.")
            self.profile_df = load_dataframe(self.profile_file,
                                             header=0, index_col=0)

        if self.ct_expr_df is None:
            # Load the celltype expression file.
            print("Loading cell type expression matrix.")
            self.ct_expr_df = load_dataframe(self.ct_expr_file,
                                             header=0, index_col=0)

        # Z-score transform the signature profile.
        profile_df = self.normalize(self.profile_df)

        print("Shifting data to be positive.")
        # Shift the data to be positive.
        if profile_df.values.min() < 0:
            print("\tshifting profile")
            profile_df = profile_df + abs(profile_df.values.min())

        expr_df = self.ct_expr_df.copy()
        if expr_df.values.min() < 0:
            print("\tshifting expression")
            expr_df = expr_df + abs(expr_df.values.min())

        # Filter on overlap.
        overlap = np.intersect1d(profile_df.index, expr_df.index)
        profile_df = profile_df.loc[overlap, :]
        expr_df = expr_df.loc[overlap, :]

        # Set index name identical.
        profile_df.index.name = "-"
        expr_df.index.name = "-"

        # Check if identical.
        if not profile_df.index.equals(expr_df.index):
            print("Invalid order.")
            exit()

        print("Profile shape: {}".format(profile_df.shape))
        print("Expression shape: {}".format(expr_df.shape))

        # Perform deconvolution per sample.
        print("Performing partial deconvolution.")
        decon_data = []
        residuals_data = []
        for _, sample in expr_df.T.iterrows():
            proportions, rnorm = self.nnls(profile_df, sample)
            decon_data.append(proportions)
            residuals_data.append(rnorm)

        decon_df = pd.DataFrame(decon_data,
                                index=expr_df.columns,
                                columns=["{}NNLS_{}".format(*x.split("_")) for x in profile_df.columns])

        print("Estimated weights:")
        print(decon_df)
        print(decon_df.mean(axis=0))

        # Make the weights sum up to 1.
        decon_df = self.sum_to_one(decon_df)
        print("Estimated proportions:")
        print(decon_df)

        # Construct a Series for the residuals.
        residuals_df = pd.Series(residuals_data, index=expr_df.columns)
        print(residuals_df)
        print("Average residual: {:.2f}".format(residuals_df.mean()))

        return decon_df

    @staticmethod
    def normalize(df):
        out_df = df.copy()
        out_df = out_df.loc[out_df.std(axis=1) > 0, :]
        out_df = out_df.subtract(out_df.mean(axis=1), axis=0).divide(out_df.std(axis=1), axis=0)
        return out_df

    @staticmethod
    def nnls(A, b):
        return nnls(A, b)

    @staticmethod
    def sum_to_one(X):
        return X.divide(X.sum(axis=1), axis=0)

    def save(self):
        save_dataframe(df=self.deconvolution, outpath=self.outpath,
                       index=True, header=True)

    def clear_variables(self):
        self.profile_file = None
        self.profile_df = None
        self.ct_expr_file = None
        self.ct_expr_df = None
        self.force = None

    def get_deconvolution(self):
        return self.deconvolution

    def print_arguments(self):
        print("Arguments:")
        if self.profile_df is not None:
            print("  > Celltype profile: {}".format(self.profile_df.shape))
        else:
            print("  > Celltype profile input file: {}".format(self.profile_file))
        if self.ct_expr_df is not None:
            print("  > Celltype expression: {}".format(self.ct_expr_df.shape))
        else:
            print("  > Celltype expression input path: {}".format(self.ct_expr_file))
        print("  > Deconvolution output file: {}".format(self.outpath))
        print("  > Force: {}".format(self.force))
        print("")
